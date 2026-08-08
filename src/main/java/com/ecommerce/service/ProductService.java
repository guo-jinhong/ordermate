package com.ecommerce.service;

import com.ecommerce.dto.ProductDTO;
import com.ecommerce.entity.Product;
import org.springframework.data.domain.Page;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public interface ProductService {
    ProductDTO createProduct(ProductDTO productDTO);
    ProductDTO updateProduct(Long productId, ProductDTO productDTO);
    ProductDTO getProductById(Long productId);
    List<ProductDTO> getAllProducts();
    List<ProductDTO> getProductsByCategory(Long categoryId);
    List<ProductDTO> searchProducts(String keyword);
    Page<ProductDTO> searchProducts(String keyword, int page, int size);
    Page<ProductDTO> searchProducts(String keyword, int page, int size, BigDecimal minPrice, BigDecimal maxPrice, Boolean inStock, LocalDateTime createdAfter);
    void deleteProduct(Long productId);
    Product getProductEntityById(Long productId);
    Product getProductEntityForUpdate(Long productId);
}
