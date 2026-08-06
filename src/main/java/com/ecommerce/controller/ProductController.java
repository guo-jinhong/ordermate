package com.ecommerce.controller;

import com.ecommerce.dto.ProductDTO;
import com.ecommerce.dto.ApiResponse;
import com.ecommerce.service.ProductService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeParseException;
import java.util.List;

@Tag(name = "Product", description = "Product Management APIs")
@RestController
@RequestMapping("/products")
@RequiredArgsConstructor
public class ProductController {
    private final ProductService productService;

    @Operation(summary = "Create a new product (Admin only)")
    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<ProductDTO> createProduct(@Valid @RequestBody ProductDTO productDTO) {
        ProductDTO createdProduct = productService.createProduct(productDTO);
        return ApiResponse.success(createdProduct, "Product created successfully");
    }

    @Operation(summary = "Update product")
    @PutMapping("/{productId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<ProductDTO> updateProduct(
            @PathVariable Long productId,
            @Valid @RequestBody ProductDTO productDTO) {
        ProductDTO updatedProduct = productService.updateProduct(productId, productDTO);
        return ApiResponse.success(updatedProduct, "Product updated successfully");
    }

    @Operation(summary = "Get product by ID")
    @GetMapping("/{productId}")
    public ApiResponse<ProductDTO> getProduct(@PathVariable Long productId) {
        ProductDTO product = productService.getProductById(productId);
        return ApiResponse.success(product);
    }

    @Operation(summary = "Get all products")
    @GetMapping
    public ApiResponse<List<ProductDTO>> getAllProducts() {
        List<ProductDTO> products = productService.getAllProducts();
        return ApiResponse.success(products);
    }

    @Operation(summary = "Get products by category")
    @GetMapping("/category/{categoryId}")
    public ApiResponse<List<ProductDTO>> getProductsByCategory(@PathVariable Long categoryId) {
        List<ProductDTO> products = productService.getProductsByCategory(categoryId);
        return ApiResponse.success(products);
    }

    @Operation(summary = "Search products (paginated)")
    @GetMapping("/search")
    public ApiResponse<Page<ProductDTO>> searchProducts(
            @Parameter(description = "Search keyword")
            @RequestParam(required = false) String keyword,
            @Parameter(description = "Minimum price")
            @RequestParam(required = false) BigDecimal minPrice,
            @Parameter(description = "Maximum price")
            @RequestParam(required = false) BigDecimal maxPrice,
            @Parameter(description = "In stock only")
            @RequestParam(required = false) Boolean inStock,
            @Parameter(description = "Created after date/time, for example 2026-07-01 or 2026-07-01T00:00:00")
            @RequestParam(required = false) String createdAfter,
            @Parameter(description = "Page number (0-based)")
            @RequestParam(defaultValue = "0") int page,
            @Parameter(description = "Page size (max 50)")
            @RequestParam(defaultValue = "10") int size) {
        
        String searchKeyword = (keyword != null && !keyword.isBlank()) ? keyword : "";
        LocalDateTime createdAfterTime = parseCreatedAfter(createdAfter);
        
        if (minPrice != null || maxPrice != null || inStock != null || createdAfterTime != null) {
            Page<ProductDTO> products = productService.searchProducts(searchKeyword, page, size, minPrice, maxPrice, inStock, createdAfterTime);
            return ApiResponse.success(products);
        } else {
            Page<ProductDTO> products = productService.searchProducts(searchKeyword, page, size);
            return ApiResponse.success(products);
        }
    }

    private LocalDateTime parseCreatedAfter(String createdAfter) {
        if (createdAfter == null || createdAfter.isBlank()) {
            return null;
        }
        String value = createdAfter.trim();
        try {
            if (value.length() == 10) {
                return LocalDate.parse(value).atStartOfDay();
            }
            return LocalDateTime.parse(value);
        } catch (DateTimeParseException exc) {
            throw new IllegalArgumentException("createdAfter must be ISO date or datetime, for example 2026-07-01");
        }
    }

    @Operation(summary = "Delete product")
    @DeleteMapping("/{productId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Void> deleteProduct(@PathVariable Long productId) {
        productService.deleteProduct(productId);
        return ApiResponse.success(null, "Product deleted successfully");
    }
}
