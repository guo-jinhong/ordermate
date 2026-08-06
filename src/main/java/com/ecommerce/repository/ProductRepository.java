package com.ecommerce.repository;

import com.ecommerce.entity.Product;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByStatusAndCategoryId(Integer status, Long categoryId);
    List<Product> findByStatus(Integer status);

    @Query("""
            SELECT p FROM Product p
            WHERE p.status = 1
              AND (
                LOWER(p.name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                OR LOWER(p.description) LIKE LOWER(CONCAT('%', :keyword, '%'))
              )
            """)
    List<Product> searchProducts(@Param("keyword") String keyword);

    @Query("""
            SELECT p FROM Product p
            WHERE p.status = 1
              AND (
                LOWER(p.name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                OR LOWER(p.description) LIKE LOWER(CONCAT('%', :keyword, '%'))
              )
            """)
    Page<Product> searchProductsPaged(@Param("keyword") String keyword, Pageable pageable);

    @Query("""
            SELECT p FROM Product p
            WHERE p.status = 1
              AND (:keyword IS NULL OR :keyword = '' OR 
                   LOWER(p.name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                   OR LOWER(p.description) LIKE LOWER(CONCAT('%', :keyword, '%')))
              AND (:minPrice IS NULL OR p.price >= :minPrice)
              AND (:maxPrice IS NULL OR p.price <= :maxPrice)
              AND (:inStock IS NULL OR 
                   (:inStock = true AND p.stock > 0) OR 
                   (:inStock = false AND p.stock = 0))
              AND (:createdAfter IS NULL OR p.createdAt >= :createdAfter)
            """)
    Page<Product> searchProductsWithFilters(
            @Param("keyword") String keyword,
            @Param("minPrice") BigDecimal minPrice,
            @Param("maxPrice") BigDecimal maxPrice,
            @Param("inStock") Boolean inStock,
            @Param("createdAfter") LocalDateTime createdAfter,
            Pageable pageable
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT p FROM Product p WHERE p.id = :productId")
    Optional<Product> findByIdForUpdate(Long productId);
}
