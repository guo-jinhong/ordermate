package com.ecommerce.service.impl;

import com.ecommerce.entity.Review;
import com.ecommerce.entity.Product;
import com.ecommerce.entity.User;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.ReviewRepository;
import com.ecommerce.service.ReviewService;
import com.ecommerce.service.ProductService;
import com.ecommerce.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

@Service
@RequiredArgsConstructor
@Transactional
public class ReviewServiceImpl implements ReviewService {
    private final ReviewRepository reviewRepository;
    private final ProductService productService;
    private final UserService userService;

    private static final ConcurrentMap<String, Boolean> likeCache = new ConcurrentHashMap<>();

    @Override
    public Review addReview(Long userId, Review review) {
        User user = userService.getUserById(userId);
        Product product = productService.getProductEntityById(review.getProduct().getId());
        
        review.setUser(user);
        review.setProduct(product);
        review.setStatus(0);
        
        return reviewRepository.save(review);
    }

    @Override
    @Transactional(readOnly = true)
    public List<Review> getProductReviews(Long productId) {
        return reviewRepository.findByProductIdAndStatus(productId, 1);
    }

    @Override
    @Transactional(readOnly = true)
    public List<Review> getUserReviews(Long userId) {
        return reviewRepository.findByUserId(userId);
    }

    @Override
    @Transactional(readOnly = true)
    public Review getReview(Long reviewId) {
        return reviewRepository.findById(reviewId)
                .orElseThrow(() -> new ResourceNotFoundException("Review not found"));
    }

    @Override
    public Review updateReview(Long userId, Long reviewId, Review review) {
        Review existingReview = getReview(reviewId);
        if (!existingReview.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Unauthorized");
        }
        
        existingReview.setRating(review.getRating());
        existingReview.setContent(review.getContent());
        
        return reviewRepository.save(existingReview);
    }

    @Override
    public void deleteReview(Long userId, Long reviewId) {
        Review review = getReview(reviewId);
        if (!review.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Unauthorized");
        }
        reviewRepository.deleteById(reviewId);
    }

    @Override
    public void likeReview(Long userId, Long reviewId) {
        String key = userId + ":" + reviewId;
        if (Boolean.TRUE.equals(likeCache.get(key))) {
            throw new BusinessException("You have already liked this review");
        }
        Review review = getReview(reviewId);
        review.setLikeCount(review.getLikeCount() + 1);
        reviewRepository.save(review);
        likeCache.put(key, true);
    }

    @Override
    @Transactional(readOnly = true)
    public boolean hasUserLiked(Long userId, Long reviewId) {
        String key = userId + ":" + reviewId;
        return Boolean.TRUE.equals(likeCache.get(key));
    }

    @Override
    @Transactional(readOnly = true)
    public List<Review> getReviewsByStatus(Integer status) {
        if (status == null) {
            return reviewRepository.findAll();
        }
        return reviewRepository.findByStatus(status);
    }

    @Override
    public Review moderateReview(Long reviewId, Integer status) {
        Review review = getReview(reviewId);
        review.setStatus(status);
        return reviewRepository.save(review);
    }

    @Override
    public void adminDeleteReview(Long reviewId) {
        Review review = getReview(reviewId);
        reviewRepository.delete(review);
    }
}
