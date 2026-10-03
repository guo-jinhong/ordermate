package com.ecommerce.entity;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "orders", uniqueConstraints = @UniqueConstraint(name = "uk_order_user_intent", columnNames = {"user_id", "idempotency_key"}))
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNo;

    @Column(name = "idempotency_key", length = 128)
    private String idempotencyKey;

    @Column(name = "request_hash", length = 64)
    private String requestHash;

    @ManyToOne
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderItem> orderItems;

    @Column(nullable = false, precision = 10, scale = 2)
    private BigDecimal totalAmount;

    @Column(nullable = false, precision = 10, scale = 2)
    private BigDecimal discountAmount;

    @Column(nullable = false, precision = 10, scale = 2)
    private BigDecimal finalAmount;

    private String shippingAddress;

    private String shippingPhone;

    private String shippingName;

    // 0: pending, 1: paid, 2: shipped, 3: delivered, 4: cancelled
    @Column(nullable = false)
    private Integer status;

    // 0: not paid, 1: paid, 2: refunding, 3: refunded
    @Column(nullable = false)
    private Integer paymentStatus;

    private String paymentMethod;

    private LocalDateTime paidAt;

    private LocalDateTime shippedAt;

    private LocalDateTime deliveredAt;

    private String remark;

    // 订单支付超时时间，超过此时间仍未支付则系统自动取消并释放库存
    @Column(name = "expire_at")
    private LocalDateTime expireAt;

    @Column(name = "created_at", columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    private LocalDateTime createdAt;

    @Column(name = "updated_at", columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    private LocalDateTime updatedAt;

    @PrePersist
    public void prePersist() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
        this.status = 0;
        this.paymentStatus = 0;
        this.discountAmount = BigDecimal.ZERO;
    }

    @PreUpdate
    public void preUpdate() {
        this.updatedAt = LocalDateTime.now();
    }
}
