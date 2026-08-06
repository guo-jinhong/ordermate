package com.ecommerce.service;

import com.ecommerce.entity.Category;
import java.util.List;

public interface CategoryService {
    Category createCategory(Category category);
    List<Category> getAllCategories();
    Category getCategory(Long categoryId);
    Category updateCategory(Long categoryId, Category category);
    void deleteCategory(Long categoryId);
}
