package kr.ktb.silko_be.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.context.SecurityContextRepository;

class AuthControllerTest {
    @Test
    void issuesRememberMeTokenWhenRequested() {
        var authenticationManager = mock(AuthenticationManager.class);
        var securityContextRepository = mock(SecurityContextRepository.class);
        var rememberMeServices = mock(RememberMeServices.class);
        var repository = mock(AdminUserRepository.class);
        var authentication = UsernamePasswordAuthenticationToken.authenticated("admin@test.com", "", java.util.List.of());
        var request = new MockHttpServletRequest();
        var response = new MockHttpServletResponse();
        when(authenticationManager.authenticate(org.mockito.ArgumentMatchers.any())).thenReturn(authentication);
        when(repository.findByEmail("admin@test.com")).thenReturn(Optional.of(new AdminUser("admin@test.com", "hash", "관리자")));
        var controller = new AuthController(authenticationManager, securityContextRepository, rememberMeServices, repository);

        var result = controller.login(new AuthController.LoginRequest("admin@test.com", "password", true), request, response);

        assertThat(result.adminName()).isEqualTo("관리자");
        verify(rememberMeServices).loginSuccess(request, response, authentication);
    }
}
