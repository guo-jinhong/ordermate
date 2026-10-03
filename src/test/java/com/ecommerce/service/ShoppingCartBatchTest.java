package com.ecommerce.service;

import com.ecommerce.dto.CartQuantityUpdateDTO;
import com.ecommerce.entity.Product;
import com.ecommerce.entity.ShoppingCart;
import com.ecommerce.entity.User;
import com.ecommerce.repository.ShoppingCartRepository;
import com.ecommerce.service.impl.ShoppingCartServiceImpl;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.List;
import java.util.Optional;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ShoppingCartBatchTest {
    @Mock ShoppingCartRepository repository;
    @Mock ProductService productService;
    @Mock UserService userService;
    @InjectMocks ShoppingCartServiceImpl service;

    private ShoppingCart cart(long id, long owner, int quantity, int stock) {
        return ShoppingCart.builder().id(id).user(User.builder().id(owner).build())
                .product(Product.builder().stock(stock).build()).quantity(quantity).build();
    }
    private CartQuantityUpdateDTO update(long id, int quantity, int previous) {
        var dto = new CartQuantityUpdateDTO();
        dto.setCartId(id); dto.setQuantity(quantity); dto.setPreviousQuantity(previous);
        return dto;
    }
    @Test void updatesEverySelectedItem() {
        var first = cart(71, 1, 3, 10); var second = cart(72, 1, 2, 10);
        when(repository.findByIdForUpdate(71L)).thenReturn(Optional.of(first));
        when(repository.findByIdForUpdate(72L)).thenReturn(Optional.of(second));
        service.updateCartItems(1L, List.of(update(72, 1, 2), update(71, 1, 3)));
        assertThat(first.getQuantity()).isEqualTo(1);
        assertThat(second.getQuantity()).isEqualTo(1);
        verify(repository).saveAll(List.of(first, second));
    }
    @Test void secondItemStockFailureDoesNotModifyFirstItem() {
        var first = cart(71, 1, 3, 10); var second = cart(72, 1, 2, 0);
        when(repository.findByIdForUpdate(71L)).thenReturn(Optional.of(first));
        when(repository.findByIdForUpdate(72L)).thenReturn(Optional.of(second));
        assertThatThrownBy(() -> service.updateCartItems(1L, List.of(update(71, 1, 3), update(72, 1, 2))))
                .hasMessageContaining("库存不足");
        assertThat(first.getQuantity()).isEqualTo(3);
        assertThat(second.getQuantity()).isEqualTo(2);
        verify(repository, never()).saveAll(any());
    }
    @Test void changedQuantityRequiresNewConfirmation() {
        when(repository.findByIdForUpdate(71L)).thenReturn(Optional.of(cart(71, 1, 5, 10)));
        assertThatThrownBy(() -> service.updateCartItems(1L, List.of(update(71, 2, 3))))
                .hasMessageContaining("重新确认");
        verify(repository, never()).saveAll(any());
    }
    @Test void anotherUsersItemCannotBeChanged() {
        when(repository.findByIdForUpdate(71L)).thenReturn(Optional.of(cart(71, 2, 3, 10)));
        assertThatThrownBy(() -> service.updateCartItems(1L, List.of(update(71, 1, 3))))
                .hasMessageContaining("无权");
        verify(repository, never()).saveAll(any());
    }
}
