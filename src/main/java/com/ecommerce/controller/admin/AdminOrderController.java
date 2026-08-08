package com.ecommerce.controller.admin;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.dto.OrderDTO;
import com.ecommerce.service.OrderPaymentService;
import com.ecommerce.service.OrderService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@Tag(name = "Admin - Order", description = "Order management APIs (admin only)")
@RestController
@RequestMapping("/admin/orders")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminOrderController {
    private final OrderService orderService;
    private final OrderPaymentService orderPaymentService;

    @Operation(summary = "List all orders (paginated, optional status filter)")
    @GetMapping
    public ApiResponse<Page<OrderDTO>> listOrders(
            @Parameter(description = "Filter by order status (0:pending 1:paid 2:shipped 3:delivered 4:cancelled)")
            @RequestParam(required = false) Integer status,
            @Parameter(description = "Page number (0-based)")
            @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size")
            @RequestParam(defaultValue = "10") int size) {
        return ApiResponse.success(orderService.getAllOrders(status, page, size));
    }

    @Operation(summary = "List all orders (non-paginated, for backward compatibility)")
    @GetMapping("/all")
    public ApiResponse<List<OrderDTO>> listAllOrders(
            @RequestParam(required = false) Integer status) {
        return ApiResponse.success(orderService.getAllOrders(status));
    }

    @Operation(summary = "Get order detail")
    @GetMapping("/{orderId}")
    public ApiResponse<OrderDTO> getOrder(@PathVariable Long orderId) {
        return ApiResponse.success(orderService.getOrderById(orderId));
    }

    @Operation(summary = "Update order status (1:paid 2:shipped 3:delivered 4:cancelled)")
    @PutMapping("/{orderId}/status")
    public ApiResponse<OrderDTO> updateStatus(
            @PathVariable Long orderId,
            @RequestParam Integer status) {
        return ApiResponse.success(orderService.updateOrderStatus(orderId, status), "Order status updated");
    }

    @Operation(summary = "Initiate refund for a paid order")
    @PostMapping("/{orderId}/refund")
    public ApiResponse<Void> initiateRefund(@PathVariable Long orderId) {
        orderPaymentService.initiateRefund(orderId);
        return ApiResponse.success(null, "Refund initiated");
    }

    @Operation(summary = "Complete refund and restore stock")
    @PostMapping("/{orderId}/refund/complete")
    public ApiResponse<OrderDTO> completeRefund(@PathVariable Long orderId) {
        OrderDTO order = orderPaymentService.completeRefund(orderId);
        return ApiResponse.success(order, "Refund completed and stock restored");
    }
}
