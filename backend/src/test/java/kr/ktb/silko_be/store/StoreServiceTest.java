package kr.ktb.silko_be.store;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.List;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.auth.AdminUserRepository;
import kr.ktb.silko_be.common.ApiException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class StoreServiceTest {
    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void rejectsSecondStoreForSameAdmin() {
        var stores = mock(StoreRepository.class);
        var admins = mock(AdminUserRepository.class);
        var admin = new AdminUser("admin@test.com", "hash", "관리자");
        SecurityContextHolder.getContext().setAuthentication(
            UsernamePasswordAuthenticationToken.authenticated(admin.getEmail(), "", List.of()));
        when(stores.findAllManagedBy(admin.getEmail())).thenReturn(List.of(new Store("기존 매장", admin)));

        var service = new StoreService(stores, admins);

        assertThatThrownBy(() -> service.create("새 매장"))
            .isInstanceOf(ApiException.class)
            .satisfies(error -> {
                var apiError = (ApiException) error;
                org.assertj.core.api.Assertions.assertThat(apiError.status()).isEqualTo(HttpStatus.CONFLICT);
                org.assertj.core.api.Assertions.assertThat(apiError.code()).isEqualTo("STORE_LIMIT_REACHED");
            });
        verify(stores, never()).save(org.mockito.ArgumentMatchers.any());
    }
}
