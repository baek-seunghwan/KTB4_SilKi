package kr.ktb.silko_be.store;

import java.util.List;
import java.util.UUID;
import kr.ktb.silko_be.auth.AdminUserRepository;
import kr.ktb.silko_be.common.ApiException;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StoreService {
    private final StoreRepository storeRepository;
    private final AdminUserRepository adminRepository;

    public StoreService(StoreRepository storeRepository, AdminUserRepository adminRepository) {
        this.storeRepository = storeRepository;
        this.adminRepository = adminRepository;
    }

    @Transactional(readOnly = true)
    public List<Store> listMine() {
        return storeRepository.findAllManagedBy(currentEmail());
    }

    @Transactional
    public Store create(String name) {
        var email = currentEmail();
        if (!storeRepository.findAllManagedBy(email).isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "STORE_LIMIT_REACHED", "계정당 하나의 매장만 관리할 수 있습니다.");
        }
        var admin = adminRepository.findByEmail(email).orElseThrow();
        return storeRepository.save(new Store(name.trim(), admin));
    }

    @Transactional(readOnly = true)
    public Store requireManagedStore(UUID storeId) {
        return storeRepository.findManagedById(storeId, currentEmail())
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "STORE_NOT_FOUND", "매장을 찾을 수 없습니다."));
    }

    @Transactional(readOnly = true)
    public Store requireStore(UUID storeId) {
        return storeRepository.findById(storeId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "STORE_NOT_FOUND", "매장을 찾을 수 없습니다."));
    }

    @Transactional
    public Store changeStatus(UUID storeId, OperatingStatus status) {
        var store = requireManagedStore(storeId);
        store.changeStatus(status);
        return store;
    }

    private String currentEmail() {
        return SecurityContextHolder.getContext().getAuthentication().getName();
    }
}
