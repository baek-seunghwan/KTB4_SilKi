package kr.ktb.silko_be.ai;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
public class AiReindexClient {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final URI baseUri;
    private final String internalApiKey;
    private final Duration requestTimeout;
    private final boolean enabled;

    @Autowired
    public AiReindexClient(ObjectMapper objectMapper,
                           @Value("${app.ai.base-url:http://localhost:8000}") String baseUrl,
                           @Value("${app.ai.internal-api-key:}") String internalApiKey,
                           @Value("${app.ai.connect-timeout:1s}") Duration connectTimeout,
                           @Value("${app.ai.reindex-request-timeout:3s}") Duration requestTimeout,
                           @Value("${app.ai.reindex-enabled:false}") boolean enabled) {
        this(HttpClient.newBuilder().connectTimeout(connectTimeout).build(), objectMapper,
            baseUrl, internalApiKey, requestTimeout, enabled);
    }

    AiReindexClient(HttpClient httpClient, ObjectMapper objectMapper, String baseUrl,
                    String internalApiKey, Duration requestTimeout, boolean enabled) {
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
        this.baseUri = URI.create(baseUrl.endsWith("/") ? baseUrl : baseUrl + "/");
        this.internalApiKey = internalApiKey;
        this.requestTimeout = requestTimeout;
        this.enabled = enabled;
    }

    public void reindex(MenuReindexEvent event) {
        if (!enabled) {
            return;
        }
        if (internalApiKey.isBlank()) {
            throw new IllegalStateException("AI internal API key is required when reindexing is enabled");
        }

        var requestBody = new ReindexRequest(
            event.menuIds().stream().map(Object::toString).toList(),
            event.sourceRevision(),
            event.reason()
        );
        try {
            var request = HttpRequest.newBuilder()
                .uri(baseUri.resolve("ai/internal/v1/stores/" + event.storeId() + "/reindex"))
                .timeout(requestTimeout)
                .header("Content-Type", "application/json")
                .header("X-Internal-API-Key", internalApiKey)
                .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(requestBody)))
                .build();
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new IllegalStateException("AI reindex request failed with status " + response.statusCode());
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("AI reindex request was interrupted", exception);
        } catch (JacksonException | java.io.IOException exception) {
            throw new IllegalStateException("AI reindex request failed", exception);
        }
    }

    record ReindexRequest(List<String> menuIds, long sourceRevision, String reason) {}
}
