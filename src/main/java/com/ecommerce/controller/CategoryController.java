package com.ecommerce.controller;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.entity.Category;
import com.ecommerce.service.CategoryService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.List;

@Tag(name = "Category", description = "Product Category APIs")
@RestController
@RequestMapping("/categories")
@RequiredArgsConstructor
public class CategoryController {
    private final CategoryService categoryService;

    @Operation(summary = "Create a new category (Admin only)")
    @PostMapping
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Category> createCategory(@Valid @RequestBody Category category) {
        Category savedCategory = categoryService.createCategory(category);
        return ApiResponse.success(savedCategory, "Category created successfully");
    }

    @Operation(summary = "Get all categories")
    @GetMapping
    public ApiResponse<List<Category>> getAllCategories() {
        List<Category> categories = categoryService.getAllCategories();
        return ApiResponse.success(categories);
    }

    @Operation(summary = "Get category by ID")
    @GetMapping("/{categoryId}")
    public ApiResponse<Category> getCategory(@PathVariable Long categoryId) {
        Category category = categoryService.getCategory(categoryId);
        return ApiResponse.success(category);
    }

    @Operation(summary = "Update category (Admin only)")
    @PutMapping("/{categoryId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Category> updateCategory(
            @PathVariable Long categoryId,
            @Valid @RequestBody Category category) {
        Category updatedCategory = categoryService.updateCategory(categoryId, category);
        return ApiResponse.success(updatedCategory, "Category updated successfully");
    }

    @Operation(summary = "Delete category (Admin only)")
    @DeleteMapping("/{categoryId}")
    @PreAuthorize("hasRole('ADMIN')")
    public ApiResponse<Void> deleteCategory(@PathVariable Long categoryId) {
        categoryService.deleteCategory(categoryId);
        return ApiResponse.success(null, "Category deleted successfully");
    }
}
