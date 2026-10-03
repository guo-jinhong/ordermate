package com.ecommerce.integration;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.Connection;
import java.sql.ResultSet;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers(disabledWithoutDocker = true)
class FlywayMigrationContainerTest {
    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.0");

    @Test
    void migrationsCreateTheBusinessSchemaOnRealMysql() throws Exception {
        Flyway.configure()
                .dataSource(MYSQL.getJdbcUrl(), MYSQL.getUsername(), MYSQL.getPassword())
                .load()
                .migrate();

        try (Connection connection = MYSQL.createConnection("");
             ResultSet tables = connection.getMetaData().getTables(MYSQL.getDatabaseName(), null, "%", new String[]{"TABLE"})) {
            Set<String> actual = new java.util.HashSet<>();
            while (tables.next()) actual.add(tables.getString("TABLE_NAME"));
            Set<String> expected = Stream.of("users", "categories", "products", "addresses",
                    "shopping_carts", "orders", "order_items", "reviews", "flyway_schema_history")
                    .collect(Collectors.toSet());
            assertThat(actual).containsAll(expected);
            try (ResultSet columns = connection.getMetaData().getColumns(MYSQL.getDatabaseName(), null, "orders", "%")) {
                Set<String> names = new java.util.HashSet<>();
                while (columns.next()) names.add(columns.getString("COLUMN_NAME"));
                assertThat(names).contains("idempotency_key", "request_hash");
            }
            try (ResultSet indexes = connection.getMetaData().getIndexInfo(MYSQL.getDatabaseName(), null, "orders", true, false)) {
                Set<String> names = new java.util.HashSet<>();
                while (indexes.next()) names.add(indexes.getString("INDEX_NAME"));
                assertThat(names).contains("uk_order_user_intent");
            }
        }
    }
}
