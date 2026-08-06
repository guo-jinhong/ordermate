package com.ecommerce.repository;

import com.ecommerce.entity.Review;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;

@Repository
public interface ReviewRepository extends JpaRepository<Review, Long> {
    List<Review> findByProductId(Long productId);
    List<Review> findByProductIdAndStatus(Long productId, Integer status);
    List<Review> findByUserId(Long userId);
    List<Review> findByStatus(Integer status);
}