package com.ecommerce.service;

import com.ecommerce.dto.CreateOrderDTO;
import com.ecommerce.dto.OrderDTO;
import com.ecommerce.dto.OrderItemDTO;
import com.ecommerce.entity.Address;
import com.ecommerce.entity.Order;
import com.ecommerce.entity.OrderItem;
import com.ecommerce.entity.Product;
import com.ecommerce.entity.User;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.AddressRepository;
import com.ecommerce.repository.OrderItemRepository;
import com.ecommerce.repository.OrderRepository;
import com.ecommerce.service.impl.OrderServiceImpl;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class OrderServiceTest {

    @Mock private com.ecommerce.repository.UserRepository userRepository;
    @Mock private OrderRepository orderRepository;
    @Mock private OrderItemRepository orderItemRepository;
    @Mock private AddressRepository addressRepository;
    @Mock private UserService userService;
    @Mock private ProductService productService;
    @Mock private ShoppingCartService shoppingCartService;
    @Mock private OrderPaymentService orderPaymentService;

    @InjectMocks
    private OrderServiceImpl orderService;

    private User user;
    private Address address;
    private Product product;

    @BeforeEach
    void setUp() {
        user = User.builder().id(1L).username("alice").build();
        address = Address.builder()
                .id(1L).user(user).name("Alice").phone("13800000001")
                .province("Beijing").city("Beijing").district("Chaoyang")
                .address("1 Sample St").build();
        product = Product.builder()
                .id(10L).name("Phone")
                .price(new BigDecimal("100.00"))
                .stock(10).soldCount(0).status(1).build();
    }

    @Test
    void samePurchaseIntentReturnsSameOrderWithoutSecondStockDeduction() {
        String key = "intent_test_123456789";
        when(userRepository.findByIdForUpdate(1L)).thenReturn(Optional.of(user));
        when(addressRepository.findById(1L)).thenReturn(Optional.of(address));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);
        java.util.concurrent.atomic.AtomicReference<Order> persisted = new java.util.concurrent.atomic.AtomicReference<>();
        when(orderRepository.findByUserIdAndIdempotencyKey(1L, key)).thenAnswer(inv -> Optional.ofNullable(persisted.get()));
        when(orderRepository.save(any(Order.class))).thenAnswer(inv -> {
            Order order = inv.getArgument(0);
            order.setId(100L);
            persisted.set(order);
            return order;
        });
        when(orderItemRepository.save(any(OrderItem.class))).thenAnswer(inv -> inv.getArgument(0));
        CreateOrderDTO request = CreateOrderDTO.builder().idempotencyKey(key).addressId(1L).paymentMethod("DEMO")
                .items(List.of(OrderItemDTO.builder().productId(10L).quantity(2).build())).build();
        OrderDTO first = orderService.createOrder(1L, request);
        OrderDTO second = orderService.createOrder(1L, request);
        assertThat(second.getId()).isEqualTo(first.getId());
        assertThat(product.getStock()).isEqualTo(8);
        verify(orderRepository, times(1)).save(any(Order.class));
        verify(productService, times(1)).getProductEntityForUpdate(10L);
        request.getItems().get(0).setQuantity(3);
        assertThatThrownBy(() -> orderService.createOrder(1L, request)).isInstanceOf(BusinessException.class)
                .hasMessageContaining("different order details");
        assertThat(product.getStock()).isEqualTo(8);
    }

    @Test
    void reversedMultiProductOrderLocksProductsInStableOrder() {
        Product second = Product.builder().id(20L).name("Other")
                .price(new BigDecimal("50.00")).stock(10).soldCount(0).status(1).build();
        when(userService.getUserById(1L)).thenReturn(user);
        when(addressRepository.findById(1L)).thenReturn(Optional.of(address));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);
        when(productService.getProductEntityForUpdate(20L)).thenReturn(second);
        when(orderRepository.save(any(Order.class))).thenAnswer(inv -> {
            Order order = inv.getArgument(0);
            order.setId(100L);
            return order;
        });
        when(orderItemRepository.save(any(OrderItem.class))).thenAnswer(inv -> inv.getArgument(0));
        orderService.createOrder(1L, CreateOrderDTO.builder().addressId(1L).paymentMethod("DEMO")
                .items(List.of(OrderItemDTO.builder().productId(20L).quantity(2).build(),
                        OrderItemDTO.builder().productId(10L).quantity(1).build())).build());
        var locks = inOrder(productService);
        locks.verify(productService).getProductEntityForUpdate(10L);
        locks.verify(productService).getProductEntityForUpdate(20L);
        assertThat(product.getStock()).isEqualTo(9);
        assertThat(second.getStock()).isEqualTo(8);
    }

    @Test
    void cancellationRestoresReversedItemsInSameLockOrder() {
        Product second = Product.builder().id(20L).stock(8).soldCount(2).build();
        Order order = Order.builder().id(100L).user(user).status(0).orderItems(List.of()).build();
        product.setStock(9);
        product.setSoldCount(1);
        when(orderRepository.findByIdForUpdate(100L)).thenReturn(Optional.of(order));
        when(orderItemRepository.findByOrderId(100L)).thenReturn(List.of(
                OrderItem.builder().product(second).quantity(2).build(),
                OrderItem.builder().product(product).quantity(1).build()));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);
        when(productService.getProductEntityForUpdate(20L)).thenReturn(second);
        when(orderRepository.save(order)).thenReturn(order);
        orderService.cancelOrder(1L, 100L);
        var locks = inOrder(productService);
        locks.verify(productService).getProductEntityForUpdate(10L);
        locks.verify(productService).getProductEntityForUpdate(20L);
        assertThat(order.getStatus()).isEqualTo(4);
        assertThat(second.getStock()).isEqualTo(10);
    }

    @Test
    void purchaseIntentLookupCannotReturnAnotherUsersOrder() {
        when(orderRepository.findByUserIdAndIdempotencyKey(2L, "owner_intent")).thenReturn(Optional.empty());
        assertThatThrownBy(() -> orderService.getOrderByIdempotencyKey(2L, "owner_intent"))
                .isInstanceOf(ResourceNotFoundException.class);
    }

    @Test
    void createOrder_decrementsStockAndComputesTotal() {
        when(userService.getUserById(1L)).thenReturn(user);
        when(addressRepository.findById(1L)).thenReturn(Optional.of(address));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);
        when(orderRepository.save(any(Order.class))).thenAnswer(inv -> {
            Order o = inv.getArgument(0);
            o.setId(100L);
            return o;
        });
        when(orderItemRepository.save(any(OrderItem.class))).thenAnswer(inv -> inv.getArgument(0));

        CreateOrderDTO request = CreateOrderDTO.builder()
                .addressId(1L)
                .paymentMethod("ALIPAY")
                .items(List.of(OrderItemDTO.builder().productId(10L).quantity(2).build()))
                .build();

        OrderDTO dto = orderService.createOrder(1L, request);

        assertThat(dto.getId()).isEqualTo(100L);
        assertThat(dto.getTotalAmount()).isEqualByComparingTo("200.00");
        assertThat(dto.getFinalAmount()).isEqualByComparingTo("200.00");
        assertThat(product.getStock()).isEqualTo(8);
        assertThat(product.getSoldCount()).isEqualTo(2);
        verify(shoppingCartService).removeProductsFromCart(eq(1L), any(java.util.List.class));
    }

    @Test
    void createOrder_addressNotOwnedByUser_throws() {
        Address other = Address.builder().id(2L).user(User.builder().id(99L).build())
                .province("X").city("X").district("X").address("X").phone("1").name("X").build();
        when(userService.getUserById(1L)).thenReturn(user);
        when(addressRepository.findById(2L)).thenReturn(Optional.of(other));

        CreateOrderDTO request = CreateOrderDTO.builder()
                .addressId(2L).paymentMethod("ALIPAY")
                .items(List.of(OrderItemDTO.builder().productId(10L).quantity(1).build()))
                .build();

        assertThatThrownBy(() -> orderService.createOrder(1L, request))
                .isInstanceOf(BusinessException.class);
        verify(orderRepository, never()).save(any());
    }

    @Test
    void createOrder_outOfStock_throws() {
        when(userService.getUserById(1L)).thenReturn(user);
        when(addressRepository.findById(1L)).thenReturn(Optional.of(address));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);

        CreateOrderDTO request = CreateOrderDTO.builder()
                .addressId(1L).paymentMethod("ALIPAY")
                .items(List.of(OrderItemDTO.builder().productId(10L).quantity(11).build()))
                .build();

        assertThatThrownBy(() -> orderService.createOrder(1L, request))
                .isInstanceOf(BusinessException.class)
                .hasMessageContaining("out of stock");
    }

    @Test
    void createOrder_emptyItems_throws() {
        when(userService.getUserById(1L)).thenReturn(user);
        when(addressRepository.findById(1L)).thenReturn(Optional.of(address));

        CreateOrderDTO request = CreateOrderDTO.builder()
                .addressId(1L).paymentMethod("ALIPAY")
                .items(List.of())
                .build();

        assertThatThrownBy(() -> orderService.createOrder(1L, request))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void cancelOrder_restoresStock() {
        Order order = Order.builder().id(100L).user(user).status(0)
                .totalAmount(new BigDecimal("200.00"))
                .finalAmount(new BigDecimal("200.00"))
                .discountAmount(BigDecimal.ZERO)
                .orderItems(List.of()).build();
        OrderItem item = OrderItem.builder().product(product).quantity(2).build();
        product.setStock(8);
        product.setSoldCount(2);

        when(orderRepository.findByIdForUpdate(100L)).thenReturn(Optional.of(order));
        when(orderItemRepository.findByOrderId(100L)).thenReturn(List.of(item));
        when(productService.getProductEntityForUpdate(10L)).thenReturn(product);
        when(orderRepository.save(any(Order.class))).thenAnswer(inv -> inv.getArgument(0));

        orderService.cancelOrder(1L, 100L);

        assertThat(order.getStatus()).isEqualTo(4);
        assertThat(product.getStock()).isEqualTo(10);
        assertThat(product.getSoldCount()).isEqualTo(0);
    }

    @Test
    void cancelOrder_notPending_throws() {
        Order order = Order.builder().id(100L).user(user).status(1).orderItems(List.of()).build();
        when(orderRepository.findByIdForUpdate(100L)).thenReturn(Optional.of(order));

        assertThatThrownBy(() -> orderService.cancelOrder(1L, 100L))
                .isInstanceOf(BusinessException.class);
    }

    @Test
    void confirmPayment_delegatesToPaymentService() {
        OrderDTO expected = OrderDTO.builder().id(100L).build();
        Order order = Order.builder().id(100L).user(user).status(0).build();
        when(orderRepository.findById(100L)).thenReturn(Optional.of(order));
        when(orderPaymentService.confirmPayment(100L)).thenReturn(expected);

        OrderDTO result = orderService.confirmPayment(1L, 100L);

        assertThat(result).isSameAs(expected);
        verify(orderPaymentService).confirmPayment(100L);
    }

    @Test
    void getUserOrderById_otherUser_throws() {
        Order order = Order.builder()
                .id(100L)
                .user(User.builder().id(2L).build())
                .build();
        when(orderRepository.findById(100L)).thenReturn(Optional.of(order));

        assertThatThrownBy(() -> orderService.getUserOrderById(1L, 100L))
                .isInstanceOf(BusinessException.class)
                .extracting("code")
                .isEqualTo(403);
    }

    @Test
    void cancelOrder_otherUser_doesNotChangeOrderOrStock() {
        Order order = Order.builder()
                .id(100L)
                .user(User.builder().id(2L).build())
                .status(0)
                .build();
        when(orderRepository.findByIdForUpdate(100L)).thenReturn(Optional.of(order));

        assertThatThrownBy(() -> orderService.cancelOrder(1L, 100L))
                .isInstanceOf(BusinessException.class);
        verify(orderItemRepository, never()).findByOrderId(anyLong());
        verify(orderRepository, never()).save(any());
    }

    @Test
    void getOrderEntityById_notFound_throws() {
        when(orderRepository.findById(404L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> orderService.getOrderEntityById(404L))
                .isInstanceOf(ResourceNotFoundException.class);
    }
}
