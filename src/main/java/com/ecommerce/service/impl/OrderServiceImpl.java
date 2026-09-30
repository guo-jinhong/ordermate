package com.ecommerce.service.impl;

import com.ecommerce.dto.*;
import com.ecommerce.entity.*;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.*;
import com.ecommerce.service.OrderPaymentService;
import com.ecommerce.service.OrderService;
import com.ecommerce.service.UserService;
import com.ecommerce.service.ProductService;
import com.ecommerce.service.ShoppingCartService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
@Transactional
public class OrderServiceImpl implements OrderService {
    private static final int MAX_QUANTITY_PER_PRODUCT = 99;

    private final OrderRepository orderRepository;
    private final OrderItemRepository orderItemRepository;
    private final AddressRepository addressRepository;
    private final UserService userService;
    private final ProductService productService;
    private final ShoppingCartService shoppingCartService;
    private final OrderPaymentService orderPaymentService;

    /** 待支付订单超时时间（分钟），超时后系统自动取消并释放库存 */
    @Value("${order.payment-timeout-minutes:15}")
    private int paymentTimeoutMinutes;

    @Override
    public OrderDTO createOrder(Long userId, CreateOrderDTO createOrderDTO) {
        User user = userService.getUserById(userId);
        Address address = addressRepository.findById(createOrderDTO.getAddressId())
                .orElseThrow(() -> new ResourceNotFoundException("Address not found"));

        if (!address.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Address does not belong to current user");
        }

        LocalDateTime now = LocalDateTime.now();
        String orderNo = "ORD-" + System.currentTimeMillis() + "-" + UUID.randomUUID().toString().substring(0, 8);
        Order order = Order.builder()
                .orderNo(orderNo)
                .user(user)
                .shippingAddress(address.getProvince() + address.getCity() + address.getDistrict() + address.getAddress())
                .shippingPhone(address.getPhone())
                .shippingName(address.getName())
                .paymentMethod(createOrderDTO.getPaymentMethod())
                .remark(createOrderDTO.getRemark())
                .discountAmount(BigDecimal.ZERO)
                .expireAt(now.plusMinutes(paymentTimeoutMinutes))
                .build();

        BigDecimal totalAmount = BigDecimal.ZERO;
        List<OrderItem> orderItems = new java.util.ArrayList<>();

        if (createOrderDTO.getItems() == null || createOrderDTO.getItems().isEmpty()) {
            throw new BusinessException("Order must contain at least one item");
        }

        for (OrderItemDTO itemDTO : createOrderDTO.getItems()) {
            Product product = productService.getProductEntityForUpdate(itemDTO.getProductId());

            if (!Integer.valueOf(1).equals(product.getStatus())) {
                throw new BusinessException("Product " + product.getName() + " is not available");
            }

            if (itemDTO.getQuantity() > MAX_QUANTITY_PER_PRODUCT) {
                throw new BusinessException("Maximum quantity per product is " + MAX_QUANTITY_PER_PRODUCT);
            }

            if (product.getStock() < itemDTO.getQuantity()) {
                throw new BusinessException("Product " + product.getName() + " is out of stock");
            }

            BigDecimal itemTotal = product.getPrice().multiply(new BigDecimal(itemDTO.getQuantity()));
            OrderItem orderItem = OrderItem.builder()
                    .order(order)
                    .product(product)
                    .quantity(itemDTO.getQuantity())
                    .unitPrice(product.getPrice())
                    .totalPrice(itemTotal)
                    .build();

            orderItems.add(orderItem);
            totalAmount = totalAmount.add(itemTotal);

            product.setStock(product.getStock() - itemDTO.getQuantity());
            product.setSoldCount(product.getSoldCount() + itemDTO.getQuantity());
        }

        order.setTotalAmount(totalAmount);
        order.setFinalAmount(totalAmount.subtract(order.getDiscountAmount() == null ? BigDecimal.ZERO : order.getDiscountAmount()));
        Order savedOrder = orderRepository.save(order);

        for (OrderItem item : orderItems) {
            item.setOrder(savedOrder);
            orderItemRepository.save(item);
        }
        savedOrder.setOrderItems(orderItems);

        List<Long> orderedProductIds = orderItems.stream()
                .map(item -> item.getProduct().getId())
                .collect(Collectors.toList());
        shoppingCartService.removeProductsFromCart(userId, orderedProductIds);

        log.info("Order created: orderNo={}, userId={}, expireAt={}", orderNo, userId, savedOrder.getExpireAt());
        return OrderDTOConverter.convertToDTO(savedOrder);
    }

    @Override
    @Transactional(readOnly = true)
    public OrderDTO getOrderById(Long orderId) {
        Order order = getOrderEntityById(orderId);
        return OrderDTOConverter.convertToDTO(order);
    }

    @Override
    @Transactional(readOnly = true)
    public OrderDTO getOrderByNo(String orderNo) {
        Order order = orderRepository.findByOrderNo(orderNo)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderNo));
        return OrderDTOConverter.convertToDTO(order);
    }

    @Override
    @Transactional(readOnly = true)
    public OrderDTO getUserOrderById(Long userId, Long orderId) {
        return OrderDTOConverter.convertToDTO(getOwnedOrder(userId, orderId));
    }

    @Override
    @Transactional(readOnly = true)
    public OrderDTO getUserOrderByNo(Long userId, String orderNo) {
        Order order = orderRepository.findByOrderNo(orderNo)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderNo));
        verifyOwnership(order, userId);
        return OrderDTOConverter.convertToDTO(order);
    }

    @Override
    @Transactional(readOnly = true)
    public List<OrderDTO> getUserOrders(Long userId) {
        return orderRepository.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(OrderDTOConverter::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional(readOnly = true)
    public Page<OrderDTO> getUserOrders(Long userId, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        return orderRepository.findByUserIdOrderByCreatedAtDesc(userId, pageable)
                .map(OrderDTOConverter::convertToDTO);
    }

    @Override
    public OrderDTO updateOrderStatus(Long orderId, Integer status) {
        Order order = getOrderEntityById(orderId);
        validateStatusTransition(order.getStatus(), status);
        order.setStatus(status);

        if (status == 2) {
            order.setShippedAt(LocalDateTime.now());
        } else if (status == 3) {
            order.setDeliveredAt(LocalDateTime.now());
        }

        Order updatedOrder = orderRepository.save(order);
        return OrderDTOConverter.convertToDTO(updatedOrder);
    }

    @Override
    public OrderDTO cancelOrder(Long userId, Long orderId) {
        Order order = orderRepository.findByIdForUpdate(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderId));
        verifyOwnership(order, userId);

        if (order.getStatus() != 0) {
            throw new BusinessException("Only pending orders can be cancelled");
        }

        releaseStock(orderId);

        order.setStatus(4);
        Order cancelledOrder = orderRepository.save(order);
        log.info("Order cancelled by user: orderId={}, userId={}", orderId, userId);
        return OrderDTOConverter.convertToDTO(cancelledOrder);
    }

    @Override
    public boolean cancelExpiredOrder(Long orderId) {
        // 幂等更新：仅当订单仍为待支付时才取消。返回影响行数，0 表示已被其他线程/实例处理
        int affected = orderRepository.cancelIfPending(orderId, LocalDateTime.now());
        if (affected == 0) {
            log.debug("Order already processed by another instance: orderId={}", orderId);
            return false;
        }

        // 释放库存。cancelIfPending 已通过乐观更新保证只有一个实例能执行到此处。
        // 若库存释放失败，异常触发事务回滚，订单状态恢复为 pending，下次轮询自动重试。
        releaseStock(orderId);
        log.info("Expired order auto-cancelled and stock released: orderId={}", orderId);
        return true;
    }

    @Override
    public OrderDTO confirmPayment(Long userId, Long orderId) {
        getOwnedOrder(userId, orderId);
        return orderPaymentService.confirmPayment(orderId);
    }

    @Override
    @Transactional(readOnly = true)
    public List<OrderDTO> getAllOrders(Integer status) {
        if (status != null) {
            return orderRepository.findByStatusOrderByCreatedAtDesc(status, PageRequest.of(0, 1000)).getContent().stream()
                    .map(OrderDTOConverter::convertToDTO)
                    .collect(Collectors.toList());
        }
        return orderRepository.findAllByOrderByCreatedAtDesc(PageRequest.of(0, 1000)).getContent().stream()
                .map(OrderDTOConverter::convertToDTO)
                .collect(Collectors.toList());
    }

    @Override
    @Transactional(readOnly = true)
    public Page<OrderDTO> getAllOrders(Integer status, int page, int size) {
        Pageable pageable = PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "createdAt"));
        if (status != null) {
            return orderRepository.findByStatusOrderByCreatedAtDesc(status, pageable)
                    .map(OrderDTOConverter::convertToDTO);
        }
        return orderRepository.findAllByOrderByCreatedAtDesc(pageable)
                .map(OrderDTOConverter::convertToDTO);
    }

    @Override
    @Transactional(readOnly = true)
    public Order getOrderEntityById(Long orderId) {
        return orderRepository.findById(orderId)
                .orElseThrow(() -> new ResourceNotFoundException("Order not found: " + orderId));
    }

    private Order getOwnedOrder(Long userId, Long orderId) {
        Order order = getOrderEntityById(orderId);
        verifyOwnership(order, userId);
        return order;
    }

    private void verifyOwnership(Order order, Long userId) {
        if (order.getUser() == null || !order.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Order does not belong to current user");
        }
    }

    /**
     * 释放订单占用的库存（将库存加回、销量扣回）。
     * 供用户取消和系统超时取消复用。
     */
    private void releaseStock(Long orderId) {
        List<OrderItem> items = orderItemRepository.findByOrderId(orderId);
        for (OrderItem item : items) {
            Product product = productService.getProductEntityForUpdate(item.getProduct().getId());
            product.setStock(product.getStock() + item.getQuantity());
            product.setSoldCount(product.getSoldCount() - item.getQuantity());
        }
    }

    private void validateStatusTransition(Integer currentStatus, Integer targetStatus) {
        if (targetStatus == null || targetStatus < 0 || targetStatus > 4) {
            throw new BusinessException("Invalid order status: " + targetStatus);
        }
        if (currentStatus.equals(targetStatus)) {
            throw new BusinessException("Order is already in status: " + targetStatus);
        }
        boolean valid = switch (currentStatus) {
            // pending 可转为 paid(1) 或 cancelled(4) —— 放开超时自动取消路径
            case 0 -> targetStatus == 1 || targetStatus == 4;
            case 1 -> targetStatus == 2 || targetStatus == 4;
            case 2 -> targetStatus == 3 || targetStatus == 4;
            case 3 -> false;
            case 4 -> false;
            default -> false;
        };
        if (!valid) {
            throw new BusinessException(
                    "Invalid order status transition: " + currentStatus + " -> " + targetStatus);
        }
    }
}
