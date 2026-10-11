package kr.ktb.silko_be.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class MenuReindexListener {
    private static final Logger log = LoggerFactory.getLogger(MenuReindexListener.class);

    private final AiReindexClient client;

    public MenuReindexListener(AiReindexClient client) {
        this.client = client;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void reindex(MenuReindexEvent event) {
        try {
            client.reindex(event);
        } catch (RuntimeException exception) {
            log.warn("AI menu reindex failed after menu commit: storeId={}, revision={}, reason={}",
                event.storeId(), event.sourceRevision(), event.reason(), exception);
        }
    }
}
