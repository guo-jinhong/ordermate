package com.ecommerce.service;

import com.ecommerce.dto.ProductDTO;
import com.ecommerce.entity.Category;
import com.ecommerce.entity.Product;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.CategoryRepository;
import com.ecommerce.repository.ProductRepository;
import com.ecommerce.service.impl.ProductServiceImpl;
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
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    private ProductRepository productRepository;

    @Mock
    private CategoryRepository categoryRepository;

    @InjectMocks
    private ProductServiceImpl productService;

    private Category category;
    private Product product;

    @BeforeEach
    void setUp() {
        category = Category.builder().id(1L).name("Electronics").status(1).build();
        product = Product.builder()
                .id(10L)
                .name("Phone")
                .price(new BigDecimal("999.00"))
                .stock(50)
                .soldCount(0)
                .category(category)
                .status(1)
                .build();
    }

    @Test
    void createProduct_withCategory_persists() {
        ProductDTO dto = ProductDTO.builder()
                .name("Phone")
                .price(new BigDecimal("999.00"))
                .stock(50)
                .categoryId(1L)
                .build();
        when(categoryRepository.findById(1L)).thenReturn(Optional.of(category));
        when(productRepository.save(any(Product.class))).thenAnswer(inv -> {
            Product p = inv.getArgument(0);
            p.setId(10L);
            return p;
        });

        ProductDTO created = productService.createProduct(dto);

        assertThat(created.getId()).isEqualTo(10L);
        assertThat(created.getCategoryId()).isEqualTo(1L);
        verify(productRepository).save(any(Product.class));
    }

    @Test
    void createProduct_invalidCategory_throws() {
        ProductDTO dto = ProductDTO.builder()
                .name("Phone")
                .price(new BigDecimal("999.00"))
                .stock(50)
                .categoryId(99L)
                .build();
        when(categoryRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> productService.createProduct(dto))
                .isInstanceOf(RuntimeException.class);
    }

    @Test
    void getProductById_returnsDTO() {
        when(productRepository.findById(10L)).thenReturn(Optional.of(product));

        ProductDTO dto = productService.getProductById(10L);

        assertThat(dto.getName()).isEqualTo("Phone");
        assertThat(dto.getStock()).isEqualTo(50);
    }

    @Test
    void getProductById_notFound_throws() {
        when(productRepository.findById(99L)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> productService.getProductById(99L))
                .isInstanceOf(RuntimeException.class);
    }

    @Test
    void getAllProducts_returnsOnlyOnSale() {
        when(productRepository.findByStatus(1)).thenReturn(List.of(product));

        List<ProductDTO> products = productService.getAllProducts();

        assertThat(products).hasSize(1);
        verify(productRepository).findByStatus(1);
    }

    @Test
    void updateProduct_changesFields() {
        when(productRepository.findById(10L)).thenReturn(Optional.of(product));
        when(productRepository.save(any(Product.class))).thenAnswer(inv -> inv.getArgument(0));

        ProductDTO update = ProductDTO.builder()
                .price(new BigDecimal("799.00"))
                .stock(30)
                .build();

        ProductDTO updated = productService.updateProduct(10L, update);

        assertThat(updated.getPrice()).isEqualByComparingTo("799.00");
        assertThat(updated.getStock()).isEqualTo(30);
    }

    @Test
    void deleteProduct_takesOffSale() {
        when(productRepository.findById(10L)).thenReturn(Optional.of(product));
        when(productRepository.save(any(Product.class))).thenAnswer(inv -> inv.getArgument(0));

        productService.deleteProduct(10L);

        assertThat(product.getStatus()).isEqualTo(0);
        verify(productRepository).save(product);
    }
}
