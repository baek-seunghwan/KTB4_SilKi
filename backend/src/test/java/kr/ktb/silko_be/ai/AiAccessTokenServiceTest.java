package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.Optional;
import java.util.UUID;
import kr.ktb.silko_be.auth.AdminUser;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.session.OrderSession;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.store.Store;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

class AiAccessTokenServiceTest {
    private static KeyPair keyPair;

    @BeforeAll
    static void generateRsaKeyPair() throws Exception {
        var generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        keyPair = generator.generateKeyPair();
    }

    @Test
    void issuesRs256TokenWithRequiredClaimsFromPersistedSession() {
        var now = Instant.now().truncatedTo(ChronoUnit.SECONDS);
        var store = store();
        var session = new OrderSession(store, OffsetDateTime.ofInstant(now.plusSeconds(600), ZoneOffset.UTC));
        var repository = mock(OrderSessionRepository.class);
        when(repository.findById(session.getId())).thenReturn(Optional.of(session));
        var service = service(repository, now, Duration.ofMinutes(2));

        var issued = service.issue(session.getId());
        var jwt = decoder().decode(issued.accessToken());

        assertThat(jwt.getHeaders()).containsEntry("alg", "RS256");
        assertThat(jwt.getSubject()).isEqualTo(session.getId().toString());
        assertThat(jwt.getClaimAsString("storeId")).isEqualTo(store.getId().toString());
        assertThat(jwt.getAudience()).containsExactly("ai-ws");
        assertThat(jwt.getClaimAsString("iss")).isEqualTo("silki-be");
        assertThat(jwt.getIssuedAt()).isEqualTo(now);
        assertThat(jwt.getExpiresAt()).isEqualTo(now.plusSeconds(120));
        assertThat(jwt.getId()).isNotBlank();
        assertThat(issued.expiresAt().toInstant()).isEqualTo(jwt.getExpiresAt());
    }

    @Test
    void capsTokenExpiryAtOrderSessionExpiry() {
        var now = Instant.now().truncatedTo(ChronoUnit.SECONDS);
        var sessionExpiry = now.plusSeconds(75);
        var session = new OrderSession(store(), OffsetDateTime.ofInstant(sessionExpiry, ZoneOffset.UTC));
        var repository = mock(OrderSessionRepository.class);
        when(repository.findById(session.getId())).thenReturn(Optional.of(session));

        var issued = service(repository, now, Duration.ofMinutes(2)).issue(session.getId());

        assertThat(decoder().decode(issued.accessToken()).getExpiresAt()).isEqualTo(sessionExpiry);
        assertThat(issued.expiresAt().toInstant()).isEqualTo(sessionExpiry);
    }

    @Test
    void rejectsExpiredSession() {
        var now = Instant.now().truncatedTo(ChronoUnit.SECONDS);
        var session = new OrderSession(store(), OffsetDateTime.ofInstant(now, ZoneOffset.UTC));
        var repository = mock(OrderSessionRepository.class);
        when(repository.findById(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service(repository, now, Duration.ofMinutes(2)).issue(session.getId()))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.GONE);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_EXPIRED");
            });
    }

    @Test
    void rejectsInactiveSession() {
        var now = Instant.now().truncatedTo(ChronoUnit.SECONDS);
        var session = new OrderSession(
            store(), OffsetDateTime.ofInstant(now.plusSeconds(600), ZoneOffset.UTC)
        );
        session.markOrdered();
        var repository = mock(OrderSessionRepository.class);
        when(repository.findById(session.getId())).thenReturn(Optional.of(session));

        assertThatThrownBy(() -> service(repository, now, Duration.ofMinutes(2)).issue(session.getId()))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.CONFLICT);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_NOT_ACTIVE");
            });
    }

    @Test
    void rejectsUnknownSession() {
        var repository = mock(OrderSessionRepository.class);
        var sessionId = UUID.randomUUID();
        when(repository.findById(sessionId)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service(repository, Instant.now(), Duration.ofMinutes(2)).issue(sessionId))
            .isInstanceOfSatisfying(ApiException.class, exception -> {
                assertThat(exception.status()).isEqualTo(HttpStatus.NOT_FOUND);
                assertThat(exception.code()).isEqualTo("ORDER_SESSION_NOT_FOUND");
            });
    }

    @Test
    void rejectsTtlOutsideShortLivedTokenRange() {
        var repository = mock(OrderSessionRepository.class);

        assertThatThrownBy(() -> service(repository, Instant.now(), Duration.ofSeconds(59)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("between 1 and 3 minutes");
        assertThatThrownBy(() -> service(repository, Instant.now(), Duration.ofMinutes(4)))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("between 1 and 3 minutes");
    }

    private AiAccessTokenService service(OrderSessionRepository repository, Instant now, Duration ttl) {
        var encoder = NimbusJwtEncoder.withKeyPair(
            (RSAPublicKey) keyPair.getPublic(), (RSAPrivateKey) keyPair.getPrivate()
        ).build();
        return new AiAccessTokenService(
            repository, encoder, "silki-be", "ai-ws", ttl, Clock.fixed(now, ZoneOffset.UTC)
        );
    }

    private JwtDecoder decoder() {
        return NimbusJwtDecoder.withPublicKey((RSAPublicKey) keyPair.getPublic()).build();
    }

    private Store store() {
        return new Store("강남점", new AdminUser("admin@test.com", "hash", "관리자"));
    }
}
