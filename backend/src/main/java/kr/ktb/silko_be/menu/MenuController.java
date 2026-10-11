package kr.ktb.silko_be.menu;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.Choice;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.DrinkSize;
import kr.ktb.silko_be.menu.DrinkOptions.ExtraShot;
import kr.ktb.silko_be.menu.DrinkOptions.FinalSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.OptionType;
import kr.ktb.silko_be.menu.DrinkOptions.SweetnessAdjustment;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.StoreService;
import org.springframework.data.domain.Page;
import org.springframework.http.HttpStatus;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@Validated
@RestController
@RequestMapping("/api/v1/admin/stores/{storeId}/menus")
public class MenuController {
    private final MenuService service;
    private final StoreService storeService;
    private final ImageStorage imageStorage;

    public MenuController(MenuService service, StoreService storeService, ImageStorage imageStorage) {
        this.service = service;
        this.storeService = storeService;
        this.imageStorage = imageStorage;
    }

    @GetMapping
    public PageResponse<MenuResponse> list(@PathVariable UUID storeId,
                                           @RequestParam MenuCategory category,
                                           @RequestParam(defaultValue = "0") @Min(0) int page,
                                           @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return PageResponse.from(service.list(storeId, category, page, size)
            .map(menu -> response(menu, imageStorage.url(menu.getImageKey()))));
    }

    @GetMapping("/{menuId}")
    public MenuResponse detail(@PathVariable UUID storeId, @PathVariable UUID menuId) {
        var menu = service.detail(storeId, menuId);
        return response(menu, imageStorage.url(menu.getImageKey()));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public MenuResponse create(@PathVariable UUID storeId, @Valid @RequestBody MenuRequest body) {
        var menu = service.create(storeId, body.category(), body.name(), body.description(), body.price(), body.imageKey(),
            body.availableTemperatures(), body.defaultSweetness(), body.caffeinated(), body.extraShotAvailable());
        return response(menu, imageStorage.url(menu.getImageKey()));
    }

    @PatchMapping("/{menuId}")
    public MenuResponse update(@PathVariable UUID storeId, @PathVariable UUID menuId,
                               @Valid @RequestBody MenuRequest body) {
        var menu = service.update(storeId, menuId, body.category(), body.name(), body.description(), body.price(),
            body.imageKey(), body.availableTemperatures(), body.defaultSweetness(), body.caffeinated(),
            body.extraShotAvailable());
        return response(menu, imageStorage.url(menu.getImageKey()));
    }

    @DeleteMapping("/{menuId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable UUID storeId, @PathVariable UUID menuId) {
        service.delete(storeId, menuId);
    }

    @PatchMapping("/{menuId}/sales-status")
    public MenuResponse changeSalesStatus(@PathVariable UUID storeId, @PathVariable UUID menuId,
                                          @Valid @RequestBody SalesStatusRequest body) {
        var menu = service.changeSalesStatus(storeId, menuId, body.salesStatus());
        return response(menu, imageStorage.url(menu.getImageKey()));
    }

    @PostMapping("/images")
    @ResponseStatus(HttpStatus.CREATED)
    public ImageUploadResponse upload(@PathVariable UUID storeId, @RequestPart("file") MultipartFile file) {
        storeService.requireManagedStore(storeId);
        var stored = imageStorage.upload(storeId, file);
        return new ImageUploadResponse(stored.imageKey(), stored.imageUrl());
    }

    static MenuResponse response(Menu menu, String imageUrl) {
        return new MenuResponse(menu.getId(), menu.getCategory(), menu.getName(), menu.getDescription(), menu.getPrice(),
            menu.getImageKey(), imageUrl, menu.getSalesStatus(), menu.getAvailableTemperatures(), menu.getDefaultSweetness(),
            menu.isCaffeinated(), menu.isExtraShotAvailable(), availableOptions(menu));
    }

    private static List<OptionResponse> availableOptions(Menu menu) {
        var options = new ArrayList<OptionResponse>();
        menu.getAvailableTemperatures().forEach(choice -> options.add(option(choice, null)));
        for (var choice : DrinkSize.values()) options.add(option(choice, null));
        if (menu.isExtraShotAvailable()) {
            for (var choice : ExtraShot.values()) options.add(option(choice, null));
        }
        for (var choice : SweetnessAdjustment.values()) {
            options.add(option(choice, menu.getDefaultSweetness().adjust(choice)));
        }
        return List.copyOf(options);
    }

    private static OptionResponse option(Choice choice, FinalSweetness finalSweetness) {
        return new OptionResponse(choice.type(), choice.code(), choice.displayName(),
            choice.additionalPrice(), finalSweetness);
    }

    public record MenuRequest(@NotNull MenuCategory category,
                              @NotBlank @Size(max = 50) String name,
                              @Size(max = 500) String description,
                              @Min(0) long price,
                              String imageKey,
                              @NotEmpty Set<@NotNull Temperature> availableTemperatures,
                              @NotNull DefaultSweetness defaultSweetness,
                              @NotNull Boolean caffeinated,
                              @NotNull Boolean extraShotAvailable) {}
    public record SalesStatusRequest(@NotNull SalesStatus salesStatus) {}
    public record ImageUploadResponse(String imageKey, String imageUrl) {}
    public record MenuResponse(UUID id, MenuCategory category, String name, String description, long price,
                               String imageKey, String imageUrl, SalesStatus salesStatus, Set<Temperature> availableTemperatures,
                               DefaultSweetness defaultSweetness, boolean caffeinated, boolean extraShotAvailable,
                               List<OptionResponse> availableOptions) {}
    public record OptionResponse(OptionType type, String code, String name, long additionalPrice,
                                 FinalSweetness finalSweetness) {}

    public record PageResponse<T>(List<T> content, int page, int size, long totalElements,
                                  int totalPages, boolean first, boolean last) {
        static <T> PageResponse<T> from(Page<T> page) {
            return new PageResponse<>(page.getContent(), page.getNumber(), page.getSize(),
                page.getTotalElements(), page.getTotalPages(), page.isFirst(), page.isLast());
        }
    }
}
