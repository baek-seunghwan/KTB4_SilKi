package kr.ktb.silko_be.ai;

import java.time.OffsetDateTime;
import java.util.UUID;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/order-sessions/{sessionId}/ai-token")
public class AiAccessTokenController {
    private final AiAccessTokenService service;

    public AiAccessTokenController(AiAccessTokenService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<AiAccessTokenResponse> issue(@PathVariable UUID sessionId) {
        var token = service.issue(sessionId);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .header(HttpHeaders.PRAGMA, "no-cache")
            .body(new AiAccessTokenResponse(token.accessToken(), token.expiresAt()));
    }

    public record AiAccessTokenResponse(String accessToken, OffsetDateTime expiresAt) {}
}
