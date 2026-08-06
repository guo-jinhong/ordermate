package com.ecommerce.controller;

import com.ecommerce.dto.ApiResponse;
import com.ecommerce.entity.Address;
import com.ecommerce.service.AddressService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import jakarta.validation.Valid;
import java.util.List;

@Tag(name = "Address", description = "Address Management APIs")
@RestController
@RequestMapping("/addresses")
@RequiredArgsConstructor
public class AddressController {
    private final AddressService addressService;

    @Operation(summary = "Add a new address")
    @PostMapping
    public ApiResponse<Address> addAddress(
            Authentication authentication,
            @Valid @RequestBody Address address) {
        Long userId = (Long) authentication.getPrincipal();
        Address savedAddress = addressService.addAddress(userId, address);
        return ApiResponse.success(savedAddress, "Address added successfully");
    }

    @Operation(summary = "Get user's addresses")
    @GetMapping
    public ApiResponse<List<Address>> getUserAddresses(Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        List<Address> addresses = addressService.getUserAddresses(userId);
        return ApiResponse.success(addresses);
    }

    @Operation(summary = "Get address by ID")
    @GetMapping("/{addressId}")
    public ApiResponse<Address> getAddress(
            Authentication authentication,
            @PathVariable Long addressId) {
        Long userId = (Long) authentication.getPrincipal();
        Address address = addressService.getAddress(userId, addressId);
        return ApiResponse.success(address);
    }

    @Operation(summary = "Update address")
    @PutMapping("/{addressId}")
    public ApiResponse<Address> updateAddress(
            Authentication authentication,
            @PathVariable Long addressId,
            @Valid @RequestBody Address address) {
        Long userId = (Long) authentication.getPrincipal();
        Address updatedAddress = addressService.updateAddress(userId, addressId, address);
        return ApiResponse.success(updatedAddress, "Address updated successfully");
    }

    @Operation(summary = "Delete address")
    @DeleteMapping("/{addressId}")
    public ApiResponse<Void> deleteAddress(
            Authentication authentication,
            @PathVariable Long addressId) {
        Long userId = (Long) authentication.getPrincipal();
        addressService.deleteAddress(userId, addressId);
        return ApiResponse.success(null, "Address deleted successfully");
    }

    @Operation(summary = "Set default address")
    @PostMapping("/{addressId}/set-default")
    public ApiResponse<Void> setDefaultAddress(
            Authentication authentication,
            @PathVariable Long addressId) {
        Long userId = (Long) authentication.getPrincipal();
        addressService.setDefaultAddress(userId, addressId);
        return ApiResponse.success(null, "Default address set");
    }
}
