package kr.ktb.silko_be.common;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

class SecurityConfigTest {
    @Test
    void rememberMeCookieUsesConfiguredSecureFlagBehindHttpOrigin() {
        UserDetailsService users = username -> User.withUsername(username)
            .password("unused")
            .roles("ADMIN")
            .build();
        var tokenRepository = mock(PersistentTokenRepository.class);
        var services = (PersistentTokenBasedRememberMeServices) new SecurityConfig("./data/uploads")
            .rememberMeServices("test-remember-me-key", 1209600, true, users, tokenRepository);
        var request = new MockHttpServletRequest();
        request.setSecure(false);
        var response = new MockHttpServletResponse();
        var authentication = UsernamePasswordAuthenticationToken.authenticated(
            "admin@test.com", "", List.of()
        );

        services.loginSuccess(request, response, authentication);

        var cookie = response.getCookie("remember-me");
        assertThat(cookie).isNotNull();
        assertThat(cookie.getSecure()).isTrue();
        assertThat(cookie.isHttpOnly()).isTrue();
        assertThat(cookie.getAttribute("SameSite")).isEqualTo("Strict");
    }
}
