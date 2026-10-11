package kr.ktb.silko_be.menu;

import java.util.Set;
import java.util.UUID;
import kr.ktb.silko_be.ai.MenuReindexPublisher;
import kr.ktb.silko_be.menu.DrinkOptions.DefaultSweetness;
import kr.ktb.silko_be.menu.DrinkOptions.Temperature;
import kr.ktb.silko_be.common.ApiException;
import kr.ktb.silko_be.storage.ImageStorage;
import kr.ktb.silko_be.store.StoreService;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MenuService {
    private final MenuRepository repository;
    private final StoreService storeService;
    private final ImageStorage imageStorage;
    private final MenuReindexPublisher reindexPublisher;
    private final MenuOptionService optionService;

    public MenuService(MenuRepository repository, StoreService storeService, ImageStorage imageStorage,
                       MenuReindexPublisher reindexPublisher, MenuOptionService optionService) {
        this.repository = repository;
        this.storeService = storeService;
        this.imageStorage = imageStorage;
        this.reindexPublisher = reindexPublisher;
        this.optionService = optionService;
    }

    @Transactional(readOnly = true)
    public Page<Menu> list(UUID storeId, MenuCategory category, int page, int size) {
        storeService.requireManagedStore(storeId);
        return listPublic(storeId, category, page, size);
    }

    @Transactional(readOnly = true)
    public Page<Menu> listPublic(UUID storeId, MenuCategory category, int page, int size) {
        var pageable = PageRequest.of(page, Math.min(size, 100), Sort.by(Sort.Direction.DESC, "createdAt"));
        return repository.findAllByStoreIdAndCategory(storeId, category, pageable);
    }

    @Transactional(readOnly = true)
    public Menu detail(UUID storeId, UUID menuId) {
        storeService.requireManagedStore(storeId);
        return requireMenu(storeId, menuId);
    }

    @Transactional(readOnly = true)
    public Menu getPublic(UUID storeId, UUID menuId) {
        return requireMenu(storeId, menuId);
    }

    @Transactional
    public Menu create(UUID storeId, MenuCategory category, String name, String description, long price, String imageKey,
                       Set<Temperature> temperatures, DefaultSweetness defaultSweetness, boolean caffeinated,
                       boolean extraShotAvailable) {
        var store = storeService.requireManagedStore(storeId);
        validateImageKey(storeId, imageKey);
        var menu = repository.save(new Menu(store, category, name.trim(), description, price, imageKey,
            temperatures, defaultSweetness, caffeinated, extraShotAvailable));
        optionService.createDefaults(menu);
        reindexPublisher.publish(storeId, menu.getId(), "menu.created");
        return menu;
    }

    @Transactional
    public Menu update(UUID storeId, UUID menuId, MenuCategory category, String name, String description,
                       long price, String imageKey, Set<Temperature> temperatures,
                       DefaultSweetness defaultSweetness, boolean caffeinated, boolean extraShotAvailable) {
        storeService.requireManagedStore(storeId);
        validateImageKey(storeId, imageKey);
        var menu = requireMenu(storeId, menuId);
        String previousImage = menu.getImageKey();
        menu.update(category, name.trim(), description, price, imageKey,
            temperatures, defaultSweetness, caffeinated, extraShotAvailable);
        if (previousImage != null && !previousImage.equals(imageKey)) imageStorage.delete(previousImage);
        reindexPublisher.publish(storeId, menuId, "menu.updated");
        return menu;
    }

    @Transactional
    public void delete(UUID storeId, UUID menuId) {
        storeService.requireManagedStore(storeId);
        var menu = requireMenu(storeId, menuId);
        repository.delete(menu);
        imageStorage.delete(menu.getImageKey());
        reindexPublisher.publish(storeId, menuId, "menu.deleted");
    }

    @Transactional
    public Menu changeSalesStatus(UUID storeId, UUID menuId, SalesStatus status) {
        storeService.requireManagedStore(storeId);
        var menu = requireMenu(storeId, menuId);
        menu.changeSalesStatus(status);
        reindexPublisher.publish(storeId, menuId, "menu.sales_status_changed");
        return menu;
    }

    Menu requireMenu(UUID storeId, UUID menuId) {
        return repository.findByIdAndStoreId(menuId, storeId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "MENU_NOT_FOUND", "메뉴를 찾을 수 없습니다."));
    }

    private void validateImageKey(UUID storeId, String imageKey) {
        if (imageKey != null && !imageKey.startsWith("stores/" + storeId + "/menus/")) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_IMAGE_KEY", "해당 매장의 이미지가 아닙니다.");
        }
    }
}
