package kr.ktb.silko_be.store;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/admin/stores")
public class StoreController {
    private final StoreService service;

    public StoreController(StoreService service) {
        this.service = service;
    }

    @GetMapping
    public List<StoreResponse> list() {
        return service.listMine().stream().map(StoreResponse::from).toList();
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public StoreResponse create(@Valid @RequestBody StoreCreateRequest body) {
        return StoreResponse.from(service.create(body.name()));
    }

    @GetMapping("/{storeId}/status")
    public StoreStatusResponse status(@PathVariable UUID storeId) {
        return new StoreStatusResponse(service.requireManagedStore(storeId).getOperatingStatus());
    }

    @PatchMapping("/{storeId}/status")
    public StoreStatusResponse changeStatus(@PathVariable UUID storeId,
                                            @Valid @RequestBody StoreStatusRequest body) {
        return new StoreStatusResponse(service.changeStatus(storeId, body.status()).getOperatingStatus());
    }

    public record StoreCreateRequest(@NotBlank @Size(max = 100) String name) {}
    public record StoreStatusRequest(@NotNull OperatingStatus status) {}
    public record StoreStatusResponse(OperatingStatus status) {}

    public record StoreResponse(UUID id, String name, OperatingStatus operatingStatus) {
        static StoreResponse from(Store store) {
            return new StoreResponse(store.getId(), store.getName(), store.getOperatingStatus());
        }
    }
}
