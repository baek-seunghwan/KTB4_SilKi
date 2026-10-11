package kr.ktb.silko_be.ai;

import java.util.List;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class MenuReindexPublisher {
    private final MenuReindexRevisionRepository revisionRepository;
    private final ApplicationEventPublisher eventPublisher;

    public MenuReindexPublisher(MenuReindexRevisionRepository revisionRepository,
                                ApplicationEventPublisher eventPublisher) {
        this.revisionRepository = revisionRepository;
        this.eventPublisher = eventPublisher;
    }

    public void publish(UUID storeId, UUID menuId, String reason) {
        long revision = revisionRepository.next(storeId);
        eventPublisher.publishEvent(new MenuReindexEvent(storeId, List.of(menuId), revision, reason));
    }
}
