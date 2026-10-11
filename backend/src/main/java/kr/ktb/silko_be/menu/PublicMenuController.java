package kr.ktb.silko_be.menu;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.storage.ImageStorage;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/v1/stores/{storeId}/menus")
public class PublicMenuController {
    private final MenuService service;
    private final MenuOptionService optionService;
    private final ImageStorage imageStorage;

    public PublicMenuController(MenuService service, MenuOptionService optionService, ImageStorage imageStorage) {
        this.service = service;
        this.optionService = optionService;
        this.imageStorage = imageStorage;
    }

    @GetMapping
    public MenuController.PageResponse<PublicMenuResponse> list(
        @PathVariable UUID storeId,
        @RequestParam MenuCategory category,
        @RequestParam(defaultValue = "0") @Min(0) int page,
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size
    ) {
        var menus = service.listPublic(storeId, category, page, size);
        var optionsByMenu = optionService.findByMenuIds(menus.getContent().stream().map(Menu::getId).toList());
        return MenuController.PageResponse.from(menus.map(menu -> response(menu, optionsByMenu)));
    }

    @GetMapping("/{menuId}")
    public PublicMenuResponse get(@PathVariable UUID storeId, @PathVariable UUID menuId) {
        var menu = service.getPublic(storeId, menuId);
        var optionsByMenu = optionService.findByMenuIds(List.of(menuId));
        return response(menu, optionsByMenu);
    }

    private PublicMenuResponse response(Menu menu, Map<UUID, List<MenuOptionGroup>> optionsByMenu) {
        var options = optionsByMenu.getOrDefault(menu.getId(), List.of()).stream()
            .map(OptionGroupResponse::from)
            .toList();
        var menuResponse = MenuController.response(menu, imageStorage.url(menu.getImageKey()));
        return new PublicMenuResponse(menuResponse.id(), menuResponse.category(), menuResponse.name(),
            menuResponse.description(), menuResponse.price(), menuResponse.imageUrl(), menuResponse.salesStatus(),
            menuResponse.availableTemperatures(), menuResponse.defaultSweetness(), menuResponse.caffeinated(),
            menuResponse.extraShotAvailable(), menuResponse.availableOptions(), options);
    }

    public record PublicMenuResponse(UUID id, MenuCategory category, String name, String description, long price,
                                     String imageUrl, SalesStatus salesStatus,
                                     Set<Temperature> availableTemperatures, DefaultSweetness defaultSweetness,
                                     boolean caffeinated, boolean extraShotAvailable,
                                     List<MenuController.OptionResponse> availableOptions,
                                     List<OptionGroupResponse> options) {}

    public record OptionGroupResponse(UUID id, String code, String name, boolean required,
                                      int minSelections, int maxSelections,
                                      boolean requiresSelection, UUID autoSelectedOptionId,
                                      List<OptionValueResponse> values) {
        static OptionGroupResponse from(MenuOptionGroup group) {
            var values = group.getValues().stream().map(OptionValueResponse::from).toList();
            var defaultValue = group.getValues().stream().filter(MenuOptionValue::isDefaultValue).findFirst();
            UUID autoSelectedOptionId = defaultValue.map(MenuOptionValue::getId)
                .orElseGet(() -> values.size() == 1 ? values.getFirst().id() : null);
            boolean requiresSelection = group.isRequired() && autoSelectedOptionId == null;
            return new OptionGroupResponse(group.getId(), group.getCode(), group.getName(),
                group.isRequired(), group.getMinSelections(), group.getMaxSelections(),
                requiresSelection, autoSelectedOptionId, values);
        }
    }

    public record OptionValueResponse(UUID id, String code, String name,
                                      long additionalPrice, boolean defaultValue) {
        static OptionValueResponse from(MenuOptionValue value) {
            return new OptionValueResponse(value.getId(), value.getCode(), value.getName(),
                value.getAdditionalPrice(), value.isDefaultValue());
        }
    }
}
