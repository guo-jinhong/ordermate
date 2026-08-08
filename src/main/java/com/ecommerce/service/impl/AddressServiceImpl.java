package com.ecommerce.service.impl;

import com.ecommerce.entity.Address;
import com.ecommerce.entity.User;
import com.ecommerce.exception.BusinessException;
import com.ecommerce.exception.ResourceNotFoundException;
import com.ecommerce.repository.AddressRepository;
import com.ecommerce.service.AddressService;
import com.ecommerce.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional
public class AddressServiceImpl implements AddressService {
    private final AddressRepository addressRepository;
    private final UserService userService;

    @Override
    public Address addAddress(Long userId, Address address) {
        User user = userService.getUserById(userId);
        address.setUser(user);
        return addressRepository.save(address);
    }

    @Override
    @Transactional(readOnly = true)
    public List<Address> getUserAddresses(Long userId) {
        return addressRepository.findByUserId(userId);
    }

    @Override
    @Transactional(readOnly = true)
    public Address getAddress(Long userId, Long addressId) {
        Address address = addressRepository.findById(addressId)
                .orElseThrow(() -> new ResourceNotFoundException("Address not found"));
        if (!address.getUser().getId().equals(userId)) {
            throw new BusinessException(403, "Address does not belong to current user");
        }
        return address;
    }

    @Override
    public Address updateAddress(Long userId, Long addressId, Address address) {
        Address existingAddress = getAddress(userId, addressId);
        existingAddress.setName(address.getName());
        existingAddress.setPhone(address.getPhone());
        existingAddress.setProvince(address.getProvince());
        existingAddress.setCity(address.getCity());
        existingAddress.setDistrict(address.getDistrict());
        existingAddress.setAddress(address.getAddress());
        return addressRepository.save(existingAddress);
    }

    @Override
    public void deleteAddress(Long userId, Long addressId) {
        Address address = getAddress(userId, addressId);
        addressRepository.deleteById(addressId);
    }

    @Override
    public void setDefaultAddress(Long userId, Long addressId) {
        Address address = getAddress(userId, addressId);

        addressRepository.clearDefaultByUserId(userId);
        address.setIsDefault(1);
        addressRepository.save(address);
    }
}
