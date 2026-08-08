package com.ecommerce.entity;

import com.fasterxml.jackson.annotation.JsonIgnore;
import jakarta.persistence.*;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;

@Entity
@Table(name = "addresses")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Address {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne
    @JoinColumn(name = "user_id", nullable = false)
    @JsonIgnore
    private User user;

    @Column(nullable = false)
    @NotBlank(message = "Recipient name cannot be blank")
    private String name;

    @Column(nullable = false)
    @NotBlank(message = "Phone cannot be blank")
    private String phone;

    @Column(nullable = false)
    @NotBlank(message = "Province cannot be blank")
    private String province;

    @Column(nullable = false)
    @NotBlank(message = "City cannot be blank")
    private String city;

    @Column(nullable = false)
    @NotBlank(message = "District cannot be blank")
    private String district;

    @Column(nullable = false)
    @NotBlank(message = "Address cannot be blank")
    private String address;

    @Column(columnDefinition = "INT DEFAULT 0")
    private Integer isDefault; // 0: not default, 1: default

    @Column(name = "created_at", columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    private LocalDateTime createdAt;

    @Column(name = "updated_at", columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    private LocalDateTime updatedAt;

    @PrePersist
    public void prePersist() {
        this.createdAt = LocalDateTime.now();
        this.updatedAt = LocalDateTime.now();
    }

    @PreUpdate
    public void preUpdate() {
        this.updatedAt = LocalDateTime.now();
    }
}
