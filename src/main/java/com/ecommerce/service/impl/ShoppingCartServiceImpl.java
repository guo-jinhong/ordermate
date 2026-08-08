package com.ecommerce.service.impl;

import com.ecommerce.dto.CartItemDTO;
import com.ecommerce.dto.AddToCartDTO;
import com.ecommerce.entity.ShoppingCart;
import com.ecommerce.entity.Product;
import com.ecommerce.entity.User;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.ShoppingCartRepository;
import com.ecommerce.service.ShoppingCartService;
import com.ecommerce.service.ProductService;
import com.ecommerce.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional
public class ShoppingCartServiceImpl implements ShoppingCartService {
    private final ShoppingCartRepository shoppingCartRepository;
    private final ProductService productService;
    private final UserService userService;

    private static final int MAX_QUANTITY_PER_PRODUCT = 99;

    @Override
    public void addToCart(Long userId, AddToCartDTO addToCartDTO) {
        Product product = productService.getProductEntityById(addToCartDTO.getProductId());

        if (!Integer.valueOf(1).equals(product.getStatus())) {
            throw new BusinessException("Product is not available");
        }

        if (addToCartDTO.getQuantity() > MAX_QUANTITY_PER_PRODUCT) {
            throw new BusinessException("Maximum quantity per product is " + MAX_QUANTITY_PER_PRODUCT);
        }

        if (product.getStock() < addToCartDTO.getQuantity()) {
            throw new BusinessException("Insufficient stock for product: " + product.getName());
        }

        User user = userService.getUserById(userId);

        ShoppingCart cart = shoppingCartRepository
                .findByUserIdAndProductId(userId, addToCartDTO.getProductId())
                .orElse(null);

        if (cart != null) {
            int newQuantity = cart.getQuantity() + addToCartDTO.getQuantity();
            if (newQuantity > MAX_QUANTITY_PER_PRODUCT) {
                throw new BusinessException("Maximum quantity per product is " + MAX_QUANTITY_PER_PRODUCT);
            }
            if (newQuantity > product.getStock()) {
                throw new BusinessException("Total quantity exceeds available stock for product: " + product.getName());
            }
            cart.setQuantity(newQuantity);
        } else {
            cart = ShoppingCart.builder()
                    .user(user)
                    .product(product)
                    .quantity(addToCartDTO.getQuantity())
                    .build();
        }

        shoppingCartRepository.save(cart);
    }

    @Override
    public void updateCart(Long userId, Long cartId, Integer quantity) {
        ShoppingCart cart = shoppingCartRepository.findById(cartId)
                .orElseThrow(() -> new ResourceNotFoundException("Cart item not found"));

        if (!cart.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Cart item does not belong to current user");
        }

        if (quantity <= 0) {
            shoppingCartRepository.deleteById(cartId);
        } else {
            if (quantity > MAX_QUANTITY_PER_PRODUCT) {
                throw new BusinessException("Maximum quantity per product is " + MAX_QUANTITY_PER_PRODUCT);
            }
            Product product = cart.getProduct();
            if (product.getStock() < quantity) {
                throw new BusinessException("Quantity exceeds available stock for product: " + product.getName());
            }
            cart.setQuantity(quantity);
            shoppingCartRepository.save(cart);
        }
    }

    @Override
    public void removeFromCart(Long userId, Long cartId) {
        ShoppingCart cart = shoppingCartRepository.findById(cartId)
                .orElseThrow(() -> new ResourceNotFoundException("Cart item not found"));

        if (!cart.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Cart item does not belong to current user");
        }

        shoppingCartRepository.deleteById(cartId);
    }

    @Override
    @Transactional(readOnly = true)
    public List<CartItemDTO> getCart(Long userId) {
        List<ShoppingCart> cartItems = shoppingCartRepository.findByUserId(userId);
        return cartItems.stream()
                .map(cart -> CartItemDTO.builder()
                        .cartId(cart.getId())
                        .productId(cart.getProduct().getId())
                        .productName(cart.getProduct().getName())
                        .price(cart.getProduct().getPrice())
                        .quantity(cart.getQuantity())
                        .build())
                .collect(Collectors.toList());
    }

    @Override
    public void clearCart(Long userId) {
        shoppingCartRepository.deleteByUserId(userId);
    }

    @Override
    public void removeProductsFromCart(Long userId, List<Long> productIds) {
        for (Long productId : productIds) {
            shoppingCartRepository.deleteByUserIdAndProductId(userId, productId);
        }
    }
}
