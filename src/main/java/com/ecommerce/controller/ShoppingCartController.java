package com.ecommerce.controller;

import com.ecommerce.dto.CartItemDTO;
import com.ecommerce.dto.AddToCartDTO;
import com.ecommerce.dto.ApiResponse;
import com.ecommerce.service.ShoppingCartService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.List;

@Tag(name = "Shopping Cart", description = "Shopping Cart Management APIs")
@RestController
@RequestMapping("/shopping-cart")
@RequiredArgsConstructor
public class ShoppingCartController {
    private final ShoppingCartService shoppingCartService;

    @Operation(summary = "Add product to cart")
    @PostMapping("/add")
    public ApiResponse<Void> addToCart(
            Authentication authentication,
            @Valid @RequestBody AddToCartDTO addToCartDTO) {
        Long userId = (Long) authentication.getPrincipal();
        shoppingCartService.addToCart(userId, addToCartDTO);
        return ApiResponse.success(null, "Product added to cart successfully");
    }

    @Operation(summary = "Get user's shopping cart")
    @GetMapping
    public ApiResponse<List<CartItemDTO>> getCart(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        List<CartItemDTO> cartItems = shoppingCartService.getCart(userId);
        return ApiResponse.success(cartItems);
    }

    @Operation(summary = "Update cart item quantity")
    @PutMapping("/{cartId}")
    public ApiResponse<Void> updateCart(
            Authentication authentication,
            @PathVariable Long cartId,
            @Parameter(description = "New quantity") @RequestParam Integer quantity) {
        Long userId = (Long) authentication.getPrincipal();
        shoppingCartService.updateCart(userId, cartId, quantity);
        return ApiResponse.success(null, "Cart updated successfully");
    }

    @Operation(summary = "Remove item from cart")
    @DeleteMapping("/{cartId}")
    public ApiResponse<Void> removeFromCart(
            Authentication authentication,
            @PathVariable Long cartId) {
        Long userId = (Long) authentication.getPrincipal();
        shoppingCartService.removeFromCart(userId, cartId);
        return ApiResponse.success(null, "Item removed from cart");
    }

    @Operation(summary = "Clear entire cart")
    @DeleteMapping
    public ApiResponse<Void> clearCart(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        shoppingCartService.clearCart(userId);
        return ApiResponse.success(null, "Cart cleared");
    }
}
