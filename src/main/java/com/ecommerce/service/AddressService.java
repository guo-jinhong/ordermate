package com.ecommerce.service;

import com.ecommerce.entity.Address;
import java.util.List;

public interface AddressService {
    Address addAddress(Long userId, Address address);
    List<Address> getUserAddresses(Long userId);
    Address getAddress(Long userId, Long addressId);
    Address updateAddress(Long userId, Long addressId, Address address);
    void deleteAddress(Long userId, Long addressId);
    void setDefaultAddress(Long userId, Long addressId);
}
