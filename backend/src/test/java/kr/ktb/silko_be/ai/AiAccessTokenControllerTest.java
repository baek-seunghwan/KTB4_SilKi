package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.OffsetDateTime;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

class AiAccessTokenControllerTest {
    @Test
    void returnsIssuedTokenWithoutAcceptingClientStoreId() {
        var service = mock(AiAccessTokenService.class);
        var sessionId = UUID.randomUUID();
        var expiresAt = OffsetDateTime.now().plusMinutes(2);
        when(service.issue(sessionId)).thenReturn(
            new AiAccessTokenService.IssuedToken("signed-access-token", expiresAt)
        );

        var entity = new AiAccessTokenController(service).issue(sessionId);
        var response = entity.getBody();

        assertThat(response).isNotNull();
        assertThat(response.accessToken()).isEqualTo("signed-access-token");
        assertThat(response.expiresAt()).isEqualTo(expiresAt);
        assertThat(entity.getHeaders().getCacheControl()).isEqualTo("no-store");
        assertThat(entity.getHeaders().getFirst(HttpHeaders.PRAGMA)).isEqualTo("no-cache");
    }
}
