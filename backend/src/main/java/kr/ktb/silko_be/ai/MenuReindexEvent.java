package kr.ktb.silko_be.ai;

import java.util.List;
import java.util.UUID;

public record MenuReindexEvent(UUID storeId, List<UUID> menuIds, long sourceRevision, String reason) {
    public MenuReindexEvent {
        menuIds = List.copyOf(menuIds);
    }
}
