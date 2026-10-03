package com.ecommerce.service.impl;

import com.ecommerce.dto.CartItemDTO;
import com.ecommerce.dto.AddToCartDTO;
import com.ecommerce.dto.CartQuantityUpdateDTO;
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

    // 全部校验后统一写入；任一失败由事务回滚，不允许部分成功。
    @Override
    public void updateCartItems(Long userId, List<CartQuantityUpdateDTO> items) {
        if (items == null || items.isEmpty()) throw new BusinessException("没有需要修改的购物车商品");
        if (items.stream().anyMatch(i -> i == null || i.getCartId() == null))
            throw new BusinessException("购物车商品编号不能为空");
        if (items.stream().map(CartQuantityUpdateDTO::getCartId).distinct().count() != items.size())
            throw new BusinessException("购物车商品不能重复");
        var sorted = items.stream().sorted(java.util.Comparator.comparing(CartQuantityUpdateDTO::getCartId)).toList();
        var carts = new java.util.ArrayList<ShoppingCart>();
        for (var item : sorted) {
            var cart = shoppingCartRepository.findByIdForUpdate(item.getCartId())
                    .orElseThrow(() -> new ResourceNotFoundException("购物车商品已不存在，请刷新后重试"));
            if (!cart.getUser().getId().equals(userId)) throw new BusinessException(403, "无权修改这件购物车商品");
            if (item.getQuantity() == null || item.getQuantity() < 1 || item.getQuantity() > MAX_QUANTITY_PER_PRODUCT)
                throw new BusinessException("商品数量必须为1到99件");
            if (item.getPreviousQuantity() != null && !item.getPreviousQuantity().equals(cart.getQuantity()))
                throw new BusinessException("购物车数量已发生变化，请重新确认修改");
            if (cart.getProduct().getStock() < item.getQuantity()) throw new BusinessException("商品库存不足，本次批量修改未执行");
            carts.add(cart);
        }
        for (int i = 0; i < carts.size(); i++) carts.get(i).setQuantity(sorted.get(i).getQuantity());
        shoppingCartRepository.saveAll(carts);
    }

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
