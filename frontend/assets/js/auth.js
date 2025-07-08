const API_URL = '/api';

// getCookie 함수는 더 이상 필요 없으므로 삭제합니다.

/**
 * 현재 로그인된 사용자 정보를 서버에 요청하는 함수
 */
async function getCurrentUser() {
    // HttpOnly 쿠키는 JS로 읽을 수 없으므로, 쿠키 존재 여부를 미리 확인하지 않습니다.
    // 대신, 브라우저가 자동으로 쿠키를 담아 보내줄 것을 믿고 바로 API를 호출합니다.
    try {
        const response = await fetch(`${API_URL}/auth/me`, {
            method: 'GET',
            credentials: 'include' // 이 옵션 덕분에 브라우저는 HttpOnly 쿠키를 서버로 보냅니다.
        });

        // 서버가 200 OK 응답을 주면, 유효한 세션이 있다는 의미입니다.
        if (response.ok) {
            return await response.json(); // 사용자 정보를 반환합니다.
        }
        // 401 등 다른 응답이 오면, 로그인되지 않은 것으로 간주합니다.
        return null;
    } catch (error) {
        console.error("Failed to fetch current user:", error);
        return null;
    }
}

/**
 * 로그인 상태에 따라 네비게이션 바의 UI를 변경하는 함수
 */
async function renderNavbar() {
    const authLinks = document.getElementById('auth-links');
    if (!authLinks) return;

    const user = await getCurrentUser();
    
    if (user) { // 로그인된 경우
        authLinks.innerHTML = `
            <span class="navbar-text">환영합니다, ${user.username}님!</span>
            <button id="logout-btn" class="btn" style="background: #6c757d; color: white; border: none; padding: 0.5rem; margin-left: 1rem; cursor: pointer;">로그아웃</button>`;
        
        document.getElementById('logout-btn').addEventListener('click', async () => {
            await fetch(`${API_URL}/auth/logout`, { 
                method: 'POST',
                credentials: 'include'
             });
            // 브라우저에서도 쿠키를 확실히 삭제
            document.cookie = "session_id=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            window.location.href = '/index.html';
        });
    } else { // 로그인되지 않은 경우
        authLinks.innerHTML = `
            <a href="/login.html" class="nav-link">로그인</a>
            <a href="/register.html" class="nav-link">회원가입</a>`;
    }
}