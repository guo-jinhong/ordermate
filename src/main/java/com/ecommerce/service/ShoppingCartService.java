package com.ecommerce.service;

import com.ecommerce.dto.CartItemDTO;
import com.ecommerce.dto.AddToCartDTO;
import java.util.List;

public interface ShoppingCartService {
    void addToCart(Long userId, AddToCartDTO addToCartDTO);
    void updateCart(Long userId, Long cartId, Integer quantity);
    void removeFromCart(Long userId, Long cartId);
    List<CartItemDTO> getCart(Long userId);
    void clearCart(Long userId);
    void removeProductsFromCart(Long userId, List<Long> productIds);
}
