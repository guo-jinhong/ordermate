package com.ecommerce.controller.admin;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.dto.ProductDTO;
import com.ecommerce.service.ProductService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@Tag(name = "Admin - Product", description = "Product management APIs (admin only)")
@RestController
@RequestMapping("/admin/products")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminProductController {
    private final ProductService productService;

    @Operation(summary = "Create a product")
    @PostMapping
    public ApiResponse<ProductDTO> create(@Valid @RequestBody ProductDTO productDTO) {
        return ApiResponse.success(productService.createProduct(productDTO), "Product created");
    }

    @Operation(summary = "Update a product")
    @PutMapping("/{productId}")
    public ApiResponse<ProductDTO> update(@PathVariable Long productId,
                                          @Valid @RequestBody ProductDTO productDTO) {
        return ApiResponse.success(productService.updateProduct(productId, productDTO), "Product updated");
    }

    @Operation(summary = "Take product off sale (soft delete)")
    @DeleteMapping("/{productId}")
    public ApiResponse<Void> delete(@PathVariable Long productId) {
        productService.deleteProduct(productId);
        return ApiResponse.success(null, "Product taken off sale");
    }
}
