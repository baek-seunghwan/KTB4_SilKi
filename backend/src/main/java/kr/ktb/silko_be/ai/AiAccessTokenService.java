package kr.ktb.silko_be.ai;

import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.session.OrderSessionRepository;
import kr.ktb.silko_be.session.OrderSessionStatus;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AiAccessTokenService {
    private static final Duration MINIMUM_TTL = Duration.ofMinutes(1);
    private static final Duration MAXIMUM_TTL = Duration.ofMinutes(3);

    private final OrderSessionRepository sessionRepository;
    private final JwtEncoder jwtEncoder;
    private final String issuer;
    private final String audience;
    private final Duration ttl;
    private final Clock clock;

    @Autowired
    public AiAccessTokenService(
        OrderSessionRepository sessionRepository,
        JwtEncoder jwtEncoder,
        @Value("${app.ai.jwt.issuer:silki-be}") String issuer,
        @Value("${app.ai.jwt.audience:ai-ws}") String audience,
        @Value("${app.ai.jwt.ttl:2m}") Duration ttl
    ) {
        this(sessionRepository, jwtEncoder, issuer, audience, ttl, Clock.systemUTC());
    }

    AiAccessTokenService(OrderSessionRepository sessionRepository, JwtEncoder jwtEncoder,
                         String issuer, String audience, Duration ttl, Clock clock) {
        this.sessionRepository = sessionRepository;
        this.jwtEncoder = jwtEncoder;
        this.issuer = requireText(issuer, "AI JWT issuer");
        this.audience = requireText(audience, "AI JWT audience");
        if (ttl.compareTo(MINIMUM_TTL) < 0 || ttl.compareTo(MAXIMUM_TTL) > 0) {
            throw new IllegalArgumentException("AI JWT TTL must be between 1 and 3 minutes");
        }
        this.ttl = ttl;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public IssuedToken issue(UUID sessionId) {
        var session = sessionRepository.findById(sessionId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "ORDER_SESSION_NOT_FOUND",
                "주문 세션을 찾을 수 없습니다."));
        var now = clock.instant();
        var sessionExpiresAt = session.getExpiresAt().toInstant();
        if (session.getStatus() == OrderSessionStatus.EXPIRED || !sessionExpiresAt.isAfter(now)) {
            throw new ApiException(HttpStatus.GONE, "ORDER_SESSION_EXPIRED", "주문 세션이 만료되었습니다.");
        }
        if (session.getStatus() != OrderSessionStatus.ACTIVE) {
            throw new ApiException(HttpStatus.CONFLICT, "ORDER_SESSION_NOT_ACTIVE",
                "이미 주문이 완료된 세션입니다.");
        }

        var issuedAt = now.truncatedTo(ChronoUnit.SECONDS);
        var expiresAt = issuedAt.plus(ttl);
        var sessionTokenExpiry = sessionExpiresAt.truncatedTo(ChronoUnit.SECONDS);
        if (!sessionTokenExpiry.isAfter(issuedAt)) {
            throw new ApiException(HttpStatus.GONE, "ORDER_SESSION_EXPIRED", "주문 세션이 만료되었습니다.");
        }
        if (expiresAt.isAfter(sessionTokenExpiry)) {
            expiresAt = sessionTokenExpiry;
        }
        var claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject(session.getId().toString())
            .audience(List.of(audience))
            .issuedAt(issuedAt)
            .expiresAt(expiresAt)
            .id(UUID.randomUUID().toString())
            .claim("storeId", session.getStoreId().toString())
            .build();
        var header = JwsHeader.with(SignatureAlgorithm.RS256).type("JWT").build();
        var token = jwtEncoder.encode(JwtEncoderParameters.from(header, claims)).getTokenValue();

        return new IssuedToken(token, OffsetDateTime.ofInstant(expiresAt, ZoneOffset.UTC));
    }

    private static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(name + " must not be blank");
        }
        return value;
    }

    public record IssuedToken(String accessToken, OffsetDateTime expiresAt) {}
}
