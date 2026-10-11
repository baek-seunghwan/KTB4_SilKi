package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class MenuReindexListenerTest {
    @Test
    void isolatesAiFailureFromCommittedMenuChange() {
        var client = mock(AiReindexClient.class);
        var event = new MenuReindexEvent(UUID.randomUUID(), List.of(UUID.randomUUID()), 7, "menu.updated");
        doThrow(new IllegalStateException("AI unavailable")).when(client).reindex(event);

        assertThatCode(() -> new MenuReindexListener(client).reindex(event)).doesNotThrowAnyException();
    }
}
