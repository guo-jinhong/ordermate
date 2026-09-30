package com.ecommerce.repository;

import com.ecommerce.entity.Order;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public interface OrderRepository extends JpaRepository<Order, Long> {
    Optional<Order> findByOrderNo(String orderNo);
    List<Order> findByUserIdOrderByCreatedAtDesc(Long userId);
    List<Order> findByUserIdAndStatus(Long userId, Integer status);

    Page<Order> findAllByOrderByCreatedAtDesc(Pageable pageable);

    Page<Order> findByStatusOrderByCreatedAtDesc(Integer status, Pageable pageable);

    Page<Order> findByUserIdOrderByCreatedAtDesc(Long userId, Pageable pageable);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("SELECT o FROM Order o WHERE o.id = :orderId")
    Optional<Order> findByIdForUpdate(@Param("orderId") Long orderId);

    @Query("SELECT COUNT(o) FROM Order o WHERE o.status = ?1")
    Long countByStatus(Integer status);

    @Query("SELECT SUM(o.finalAmount) FROM Order o WHERE o.paymentStatus = 1")
    java.math.BigDecimal sumPaidOrders();

    /**
     * 查询已超时且仍处于待支付状态的订单。
     * 使用 SKIP LOCKED 保证多实例部署时各节点互不阻塞、不重复处理同一订单。
     * 仅返回 status=0 且 expireAt < now 的订单，按 expireAt 升序（最紧急的先处理）。
     */
    @Query(value = "SELECT * FROM orders o WHERE o.status = 0 AND o.expire_at IS NOT NULL " +
            "AND o.expire_at < :now ORDER BY o.expire_at ASC LIMIT :limit FOR UPDATE SKIP LOCKED",
            nativeQuery = true)
    List<Order> findExpiredPendingOrders(@Param("now") LocalDateTime now, @Param("limit") int limit);

    /**
     * 幂等更新：仅当订单仍为待支付状态时才取消。
     * 通过返回影响行数判断是否取消成功（多实例并发安全）。
     * clearAutomatically + flushAutomatically 确保执行后持久化上下文与数据库一致。
     */
    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("UPDATE Order o SET o.status = 4, o.updatedAt = :now WHERE o.id = :orderId AND o.status = 0")
    int cancelIfPending(@Param("orderId") Long orderId, @Param("now") LocalDateTime now);
}
