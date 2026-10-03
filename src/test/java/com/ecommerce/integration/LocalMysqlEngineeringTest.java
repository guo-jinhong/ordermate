package com.ecommerce.integration;

import com.ecommerce.dto.CreateOrderDTO;
import com.ecommerce.dto.OrderItemDTO;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.repository.ProductRepository;
import com.ecommerce.service.*;
import com.ecommerce.service.impl.OrderServiceImpl;
import java.sql.DriverManager;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.when;

/** 显式启用时创建独立临时库；不使用、清空或迁移开发业务库。 */
@EnabledIfEnvironmentVariable(named = "ORDERMATE_MYSQL_CHECK", matches = "1")
@DataJpaTest(showSql = false, properties = {"spring.jpa.hibernate.ddl-auto=validate", "logging.level.root=WARN", "logging.level.com.ecommerce=WARN"})
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(OrderServiceImpl.class)
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class LocalMysqlEngineeringTest {
    static final String DATABASE = System.getenv().getOrDefault("ORDERMATE_MYSQL_TEST_SCHEMA",
            "ordermate_check_" + UUID.randomUUID().toString().replace("-", ""));
    static final String BASE = System.getenv("ORDERMATE_MYSQL_JDBC_BASE");
    static final String USER = System.getenv("ORDERMATE_MYSQL_USER");
    static final String PASSWORD = System.getenv("ORDERMATE_MYSQL_PASSWORD");
    static boolean created;
    @Autowired JdbcTemplate jdbc;
    @Autowired OrderService orders;
    @Autowired ProductRepository products;
    @MockBean UserService users;
    @MockBean ProductService productService;
    @MockBean ShoppingCartService cart;
    @MockBean OrderPaymentService payment;

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) throws Exception {
        if (!DATABASE.matches("ordermate_check_[a-f0-9]{32}")) throw new IllegalArgumentException("Invalid isolated test database name");
        try (var connection = DriverManager.getConnection(BASE + "/?useSSL=false&allowPublicKeyRetrieval=true", USER, PASSWORD);
             var statement = connection.createStatement()) {
            statement.execute("CREATE DATABASE `" + DATABASE + "`");
            created = true;
        }
        registry.add("spring.datasource.url", () -> BASE + "/" + DATABASE + "?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC");
        registry.add("spring.datasource.username", () -> USER);
        registry.add("spring.datasource.password", () -> PASSWORD);
    }

    @AfterAll
    static void cleanupOnlyOwnedTestDatabase() throws Exception {
        if (created && DATABASE.matches("ordermate_check_[a-f0-9]{32}")) {
            try (var connection = DriverManager.getConnection(BASE + "/?useSSL=false&allowPublicKeyRetrieval=true", USER, PASSWORD);
                 var statement = connection.createStatement()) {
                statement.execute("DROP DATABASE `" + DATABASE + "`");
            }
        }
    }

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM order_items");
        jdbc.update("DELETE FROM orders");
        jdbc.update("DELETE FROM shopping_carts");
        jdbc.update("DELETE FROM addresses");
        jdbc.update("DELETE FROM products");
        jdbc.update("DELETE FROM users");
        for (long id : List.of(1L, 2L)) {
            jdbc.update("INSERT INTO users(id,username,password,email) VALUES (?,?,?,?)", id, "test" + id, "unused", "test" + id + "@example.test");
            jdbc.update("INSERT INTO addresses(id,user_id,name,phone,province,city,district,address) VALUES (?,?, 'test','1','p','c','d','test')", id, id);
        }
        for (long id : List.of(10L, 20L)) jdbc.update("INSERT INTO products(id,name,price,stock,sold_count,status) VALUES (?, 'test', 100, 10, 0, 1)", id);
        // 服务只替换外部依赖，商品查询仍经过真实 JPA 悲观锁和同一事务。
        when(productService.getProductEntityForUpdate(anyLong())).thenAnswer(inv -> products.findByIdForUpdate(inv.getArgument(0)).orElseThrow());
    }

    CreateOrderDTO request(long user, String intent, int quantity, boolean reverse) {
        var first = OrderItemDTO.builder().productId(reverse ? 20L : 10L).quantity(quantity).build();
        var second = OrderItemDTO.builder().productId(reverse ? 10L : 20L).quantity(quantity).build();
        return CreateOrderDTO.builder().addressId(user).paymentMethod("DEMO").idempotencyKey(intent)
                .items(List.of(first, second)).build();
    }

    @Test
    void flywayUniqueConstraintIsPresent() {
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM flyway_schema_history WHERE success=1", Integer.class)).isEqualTo(2);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM information_schema.statistics WHERE table_schema=? AND table_name='orders' AND index_name='uk_order_user_intent' AND non_unique=0", Integer.class, DATABASE)).isEqualTo(2);
    }

    @Test
    void concurrentSameIntentCreatesOneOrderAndDeductsOnce() throws Exception {
        var start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(2);
        try {
            Callable<Long> create = () -> { start.await(); return orders.createOrder(1L, request(1, "same_intent_123456789", 2, true)).getId(); };
            var first = executor.submit(create);
            var second = executor.submit(create);
            start.countDown();
            assertThat(first.get(30, TimeUnit.SECONDS)).isEqualTo(second.get(30, TimeUnit.SECONDS));
            assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM orders", Integer.class)).isEqualTo(1);
            assertThat(jdbc.queryForList("SELECT stock FROM products ORDER BY id", Integer.class)).containsExactly(8, 8);
            assertThatThrownBy(() -> orders.createOrder(1L, request(1, "same_intent_123456789", 3, false))).isInstanceOf(BusinessException.class);
        } finally { executor.shutdownNow(); }
    }

    @Test
    void reversedConcurrentOrdersDoNotOversell() throws Exception {
        var start = new CountDownLatch(1);
        var executor = Executors.newFixedThreadPool(2);
        try {
            var first = executor.submit(() -> { start.await(); try { orders.createOrder(1L, request(1, "first_intent_123456789", 6, true)); return true; } catch (BusinessException ex) { return false; } });
            var second = executor.submit(() -> { start.await(); try { orders.createOrder(2L, request(2, "second_intent_123456789", 6, false)); return true; } catch (BusinessException ex) { return false; } });
            start.countDown();
            assertThat(List.of(first.get(30, TimeUnit.SECONDS), second.get(30, TimeUnit.SECONDS))).containsExactlyInAnyOrder(true, false);
            assertThat(jdbc.queryForList("SELECT stock FROM products ORDER BY id", Integer.class)).containsExactly(4, 4);
        } finally { executor.shutdownNow(); }
    }

    @Test
    void laterItemFailureRollsBackEarlierDeduction() {
        jdbc.update("UPDATE products SET stock=1 WHERE id=20");
        assertThatThrownBy(() -> orders.createOrder(1L, request(1, "rollback_intent_123456789", 2, true))).isInstanceOf(BusinessException.class);
        assertThat(jdbc.queryForList("SELECT stock FROM products ORDER BY id", Integer.class)).containsExactly(10, 1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM orders", Integer.class)).isZero();
    }
}
