package com.ecommerce.controller;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.entity.Review;
import com.ecommerce.service.ReviewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.List;

@Tag(name = "Review", description = "Product Review APIs")
@RestController
@RequestMapping("/reviews")
@RequiredArgsConstructor
public class ReviewController {
    private final ReviewService reviewService;

    @Operation(summary = "Add a review for product")
    @PostMapping
    public ApiResponse<Review> addReview(
            Authentication authentication,
            @Valid @RequestBody Review review) {
        Long userId = (Long) authentication.getPrincipal();
        Review savedReview = reviewService.addReview(userId, review);
        return ApiResponse.success(savedReview, "Review added successfully");
    }

    @Operation(summary = "Get reviews for a product")
    @GetMapping("/product/{productId}")
    public ApiResponse<List<Review>> getProductReviews(@PathVariable Long productId) {
        List<Review> reviews = reviewService.getProductReviews(productId);
        return ApiResponse.success(reviews);
    }

    @Operation(summary = "Get user's reviews")
    @GetMapping
    public ApiResponse<List<Review>> getUserReviews(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        List<Review> reviews = reviewService.getUserReviews(userId);
        return ApiResponse.success(reviews);
    }

    @Operation(summary = "Get review by ID")
    @GetMapping("/{reviewId}")
    public ApiResponse<Review> getReview(@PathVariable Long reviewId) {
        Review review = reviewService.getReview(reviewId);
        return ApiResponse.success(review);
    }

    @Operation(summary = "Update review")
    @PutMapping("/{reviewId}")
    public ApiResponse<Review> updateReview(
            Authentication authentication,
            @PathVariable Long reviewId,
            @Valid @RequestBody Review review) {
        Long userId = (Long) authentication.getPrincipal();
        Review updatedReview = reviewService.updateReview(userId, reviewId, review);
        return ApiResponse.success(updatedReview, "Review updated successfully");
    }

    @Operation(summary = "Delete review")
    @DeleteMapping("/{reviewId}")
    public ApiResponse<Void> deleteReview(
            Authentication authentication,
            @PathVariable Long reviewId) {
        Long userId = (Long) authentication.getPrincipal();
        reviewService.deleteReview(userId, reviewId);
        return ApiResponse.success(null, "Review deleted successfully");
    }

    @Operation(summary = "Like a review")
    @PostMapping("/{reviewId}/like")
    public ApiResponse<Void> likeReview(
            Authentication authentication,
            @PathVariable Long reviewId) {
        Long userId = (Long) authentication.getPrincipal();
        reviewService.likeReview(userId, reviewId);
        return ApiResponse.success(null, "Review liked");
    }
}
