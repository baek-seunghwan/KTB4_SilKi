package kr.ktb.silko_be.common;

import java.nio.file.Path;
import java.util.List;
import javax.sql.DataSource;
import kr.ktb.silko_be.auth.AdminUserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class SecurityConfig implements WebMvcConfigurer {
    private final String localStoragePath;

    public SecurityConfig(@Value("${app.storage.local-path}") String localStoragePath) {
        this.localStoragePath = localStoragePath;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            @Value("${app.cors.allowed-origin}") String allowedOrigin,
                                            RememberMeServices rememberMeServices) throws Exception {
        var cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of(allowedOrigin));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "Idempotency-Key", "If-Match", "Last-Event-ID"));
        cors.setAllowCredentials(true);
        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);

        return http
            .cors(config -> config.configurationSource(source))
            .csrf(csrf -> csrf.disable())
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .rememberMe(remember -> remember.rememberMeServices(rememberMeServices))
            .logout(logout -> logout
                .logoutUrl("/api/v1/admin/auth/logout")
                .logoutSuccessHandler(new HttpStatusReturningLogoutSuccessHandler(HttpStatus.NO_CONTENT)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/api/v1/admin/auth/login").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/v1/stores/*/orders",
                    "/api/v1/stores/*/order-sessions", "/api/v1/order-sessions/*/cart/items",
                    "/api/v1/order-sessions/*/preview", "/api/v1/order-sessions/*/orders",
                    "/api/v1/order-sessions/*/ai-token").permitAll()
                .requestMatchers(HttpMethod.PATCH, "/api/v1/order-sessions/*/cart/items/*").permitAll()
                .requestMatchers(HttpMethod.PATCH, "/api/v1/order-sessions/*/fulfillment").permitAll()
                .requestMatchers(HttpMethod.PUT, "/api/v1/order-sessions/*/cart").permitAll()
                .requestMatchers(HttpMethod.DELETE, "/api/v1/order-sessions/*/cart/items/*").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/v1/stores/*/menus",
                    "/api/v1/stores/*/menus/*",
                    "/api/v1/stores/*/order-context", "/api/v1/stores/*/status",
                    "/api/v1/order-sessions/*/cart", "/api/v1/orders/**", "/uploads/**").permitAll()
                .requestMatchers("/swagger-ui/**", "/swagger-ui.html", "/v3/api-docs/**").permitAll()
                .requestMatchers("/api/v1/admin/**").authenticated()
                .anyRequest().denyAll())
            .exceptionHandling(exceptions -> exceptions.authenticationEntryPoint((request, response, exception) -> {
                response.setStatus(401);
                response.setContentType("application/json;charset=UTF-8");
                response.getWriter().write("{\"code\":\"UNAUTHORIZED\",\"message\":\"로그인이 필요합니다.\",\"fieldErrors\":[]}");
            }))
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(AdminUserRepository repository) {
        return email -> repository.findByEmail(email)
            .map(admin -> User.withUsername(admin.getEmail())
                .password(admin.getPasswordHash())
                .roles("ADMIN")
                .build())
            .orElseThrow(() -> new org.springframework.security.core.userdetails.UsernameNotFoundException(email));
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    AuthenticationManager authenticationManager(AuthenticationConfiguration configuration) throws Exception {
        return configuration.getAuthenticationManager();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    @SuppressWarnings("removal")
    PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
        var repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        return repository;
    }

    @Bean
    RememberMeServices rememberMeServices(
        @Value("${app.security.remember-me-key}") String key,
        @Value("${app.security.remember-me-validity-seconds}") int validitySeconds,
        @Value("${server.servlet.session.cookie.secure:false}") boolean secureCookie,
        UserDetailsService userDetailsService,
        PersistentTokenRepository tokenRepository
    ) {
        var services = new PersistentTokenBasedRememberMeServices(key, userDetailsService, tokenRepository);
        services.setAlwaysRemember(true);
        services.setTokenValiditySeconds(validitySeconds);
        services.setCookieCustomizer(cookie -> {
            cookie.setAttribute("SameSite", "Strict");
            cookie.setSecure(secureCookie);
        });
        return services;
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String location = Path.of(localStoragePath).toAbsolutePath().normalize().toUri().toString();
        if (!location.endsWith("/")) location += "/";
        registry.addResourceHandler("/uploads/**").addResourceLocations(location);
    }
}
