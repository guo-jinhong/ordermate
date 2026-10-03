package com.ecommerce.repository;

import com.ecommerce.entity.ShoppingCart;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import java.util.List;
import java.util.Optional;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

@Repository
public interface ShoppingCartRepository extends JpaRepository<ShoppingCart, Long> {
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select c from ShoppingCart c where c.id = :id")
    Optional<ShoppingCart> findByIdForUpdate(@Param("id") Long id);
    List<ShoppingCart> findByUserId(Long userId);
    Optional<ShoppingCart> findByUserIdAndProductId(Long userId, Long productId);
    void deleteByUserId(Long userId);
    void deleteByUserIdAndProductId(Long userId, Long productId);
}
