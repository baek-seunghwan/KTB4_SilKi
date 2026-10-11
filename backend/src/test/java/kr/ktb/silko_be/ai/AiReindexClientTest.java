package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import tools.jackson.databind.ObjectMapper;

class AiReindexClientTest {
    private final HttpClient httpClient = mock(HttpClient.class);
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void sendsInternalReindexRequestUsingAiContract() throws Exception {
        var response = response(200);
        when(httpClient.send(any(HttpRequest.class), anyResponseHandler())).thenReturn(response);
        var client = client(true, "internal-secret");
        var storeId = UUID.randomUUID();
        var menuId = UUID.randomUUID();

        client.reindex(new MenuReindexEvent(storeId, List.of(menuId), 12, "menu.updated"));

        var requestCaptor = ArgumentCaptor.forClass(HttpRequest.class);
        verify(httpClient).send(requestCaptor.capture(), anyResponseHandler());
        var request = requestCaptor.getValue();
        assertThat(request.uri().toString())
            .isEqualTo("http://ai.test/ai/internal/v1/stores/" + storeId + "/reindex");
        assertThat(request.headers().firstValue("X-Internal-API-Key")).contains("internal-secret");
        assertThat(request.method()).isEqualTo("POST");
        assertThat(request.bodyPublisher()).isPresent();
    }

    @Test
    void skipsRequestWhenReindexingIsDisabled() throws Exception {
        var client = client(false, "");

        client.reindex(new MenuReindexEvent(UUID.randomUUID(), List.of(UUID.randomUUID()), 1, "menu.created"));

        verify(httpClient, never()).send(any(HttpRequest.class), anyResponseHandler());
    }

    @Test
    void rejectsNonSuccessfulAiResponse() throws Exception {
        var response = response(503);
        when(httpClient.send(any(HttpRequest.class), anyResponseHandler())).thenReturn(response);
        var client = client(true, "internal-secret");

        assertThatThrownBy(() -> client.reindex(
            new MenuReindexEvent(UUID.randomUUID(), List.of(UUID.randomUUID()), 1, "menu.deleted")))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("status 503");
    }

    private AiReindexClient client(boolean enabled, String apiKey) {
        return new AiReindexClient(httpClient, objectMapper, "http://ai.test", apiKey,
            Duration.ofSeconds(3), enabled);
    }

    @SuppressWarnings("unchecked")
    private HttpResponse<String> response(int status) {
        var response = (HttpResponse<String>) mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        return response;
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse.BodyHandler<String> anyResponseHandler() {
        return any(HttpResponse.BodyHandler.class);
    }
}
