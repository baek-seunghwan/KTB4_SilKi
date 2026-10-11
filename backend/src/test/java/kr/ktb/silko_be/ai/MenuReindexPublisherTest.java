package kr.ktb.silko_be.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class MenuReindexPublisherTest {
    @Test
    void publishesPersistedRevisionWithChangedMenu() {
        var revisions = mock(MenuReindexRevisionRepository.class);
        var events = mock(ApplicationEventPublisher.class);
        var publisher = new MenuReindexPublisher(revisions, events);
        var storeId = UUID.randomUUID();
        var menuId = UUID.randomUUID();
        when(revisions.next(storeId)).thenReturn(42L);

        publisher.publish(storeId, menuId, "menu.updated");

        var captor = ArgumentCaptor.forClass(MenuReindexEvent.class);
        verify(events).publishEvent(captor.capture());
        assertThat(captor.getValue().storeId()).isEqualTo(storeId);
        assertThat(captor.getValue().menuIds()).containsExactly(menuId);
        assertThat(captor.getValue().sourceRevision()).isEqualTo(42L);
        assertThat(captor.getValue().reason()).isEqualTo("menu.updated");
    }
}
