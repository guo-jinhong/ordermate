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

    @Override
    public OrderDTO createOrder(Long userId, CreateOrderDTO createOrderDTO) {
        User user = userService.getUserById(userId);
        Address address = addressRepository.findById(createOrderDTO.getAddressId())
                .orElseThrow(() -> new ResourceNotFoundException("Address not found"));

        if (!address.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Address does not belong to current user");
        }

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

        List<OrderItem> items = orderItemRepository.findByOrderId(orderId);
        for (OrderItem item : items) {
            Product product = productService.getProductEntityForUpdate(
                    item.getProduct().getId());
            product.setStock(product.getStock() + item.getQuantity());
            product.setSoldCount(product.getSoldCount() - item.getQuantity());
        }

        order.setStatus(4);
        Order cancelledOrder = orderRepository.save(order);
        return OrderDTOConverter.convertToDTO(cancelledOrder);
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

    private void validateStatusTransition(Integer currentStatus, Integer targetStatus) {
        if (targetStatus == null || targetStatus < 0 || targetStatus > 4) {
            throw new BusinessException("Invalid order status: " + targetStatus);
        }
        if (currentStatus.equals(targetStatus)) {
            throw new BusinessException("Order is already in status: " + targetStatus);
        }
        boolean valid = switch (currentStatus) {
            case 0 -> targetStatus == 1;
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
