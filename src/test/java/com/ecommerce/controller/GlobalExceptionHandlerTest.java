package com.ecommerce.controller;

import com.ecommerce.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.dao.CannotAcquireLockException;
import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {
    @Test
    void lockConflictReturnsBusinessConflictInsteadOfGenericServerError() {
        var response = new GlobalExceptionHandler().handleLockConflict(new CannotAcquireLockException("test lock contention"));
        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(response.getBody().getCode()).isEqualTo(409);
        assertThat(response.getBody().getMessage()).contains("先查看");
    }

    @Test
    void incompatibleIntentPayloadReturnsHttpConflict() {
        var response = new GlobalExceptionHandler().handleBusinessException(new BusinessException(409, "different payload"), null);
        assertThat(response.getStatusCode().value()).isEqualTo(409);
    }
}
