package com.ecommerce.controller.admin;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.entity.Review;
import com.ecommerce.service.ReviewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@Tag(name = "Admin - Review", description = "Review moderation APIs (admin only)")
@RestController
@RequestMapping("/admin/reviews")
@RequiredArgsConstructor
@PreAuthorize("hasRole('ADMIN')")
public class AdminReviewController {
    private final ReviewService reviewService;

    @Operation(summary = "List reviews by status (null = all, 0 = pending, 1 = approved)")
    @GetMapping
    public ApiResponse<List<Review>> list(@RequestParam(required = false) Integer status) {
        return ApiResponse.success(reviewService.getReviewsByStatus(status));
    }

    @Operation(summary = "Approve a review (status=1)")
    @PostMapping("/{reviewId}/approve")
    public ApiResponse<Review> approve(@PathVariable Long reviewId) {
        return ApiResponse.success(reviewService.moderateReview(reviewId, 1), "Review approved");
    }

    @Operation(summary = "Reject a review (status=0)")
    @PostMapping("/{reviewId}/reject")
    public ApiResponse<Review> reject(@PathVariable Long reviewId) {
        return ApiResponse.success(reviewService.moderateReview(reviewId, 0), "Review rejected");
    }

    @Operation(summary = "Hard-delete a review")
    @DeleteMapping("/{reviewId}")
    public ApiResponse<Void> delete(@PathVariable Long reviewId) {
        reviewService.adminDeleteReview(reviewId);
        return ApiResponse.success(null, "Review deleted");
    }
}
