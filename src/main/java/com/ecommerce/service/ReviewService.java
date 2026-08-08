package com.ecommerce.service;

import com.ecommerce.entity.Review;
import java.util.List;

public interface ReviewService {
    Review addReview(Long userId, Review review);
    List<Review> getProductReviews(Long productId);
    List<Review> getUserReviews(Long userId);
    Review getReview(Long reviewId);
    Review updateReview(Long userId, Long reviewId, Review review);
    void deleteReview(Long userId, Long reviewId);
    void likeReview(Long userId, Long reviewId);
    boolean hasUserLiked(Long userId, Long reviewId);

    // ----- admin -----
    List<Review> getReviewsByStatus(Integer status);
    Review moderateReview(Long reviewId, Integer status);
    void adminDeleteReview(Long reviewId);
}
