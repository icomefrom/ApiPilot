"""
后端测试 - 认证、个人信息
"""
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from apps.authentication.models import User


class AuthenticationTests(TestCase):
    """认证相关测试"""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@test.com', password='admin123'
        )
        self.viewer = User.objects.create_user(
            username='viewer', email='viewer@test.com', password='viewer123'
        )

    def test_login_success(self):
        """测试登录成功"""
        res = self.client.post('/api/auth/login/', {
            'username': 'admin', 'password': 'admin123'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.data)
        self.assertIn('refresh', res.data)
        self.assertIn('user', res.data)

    def test_login_wrong_password(self):
        """测试密码错误"""
        res = self.client.post('/api/auth/login/', {
            'username': 'admin', 'password': 'wrong'
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_disabled_user(self):
        """测试禁用用户登录"""
        self.viewer.is_active = False
        self.viewer.save()
        res = self.client.post('/api/auth/login/', {
            'username': 'viewer', 'password': 'viewer123'
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_profile(self):
        """测试获取个人信息"""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get('/api/auth/profile/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['username'], 'admin')

    def test_update_profile(self):
        """测试更新个人信息"""
        self.client.force_authenticate(user=self.admin)
        res = self.client.put('/api/auth/profile/', {
            'email': 'newadmin@test.com', 'phone': '13800138000'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.email, 'newadmin@test.com')

    def test_change_password(self):
        """测试修改密码"""
        self.client.force_authenticate(user=self.viewer)
        res = self.client.post('/api/auth/change-password/', {
            'old_password': 'viewer123',
            'new_password': 'newpassword1'
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.viewer.refresh_from_db()
        self.assertTrue(self.viewer.check_password('newpassword1'))

    def test_change_password_wrong_old(self):
        """测试旧密码错误"""
        self.client.force_authenticate(user=self.viewer)
        res = self.client.post('/api/auth/change-password/', {
            'old_password': 'wrong',
            'new_password': 'newpassword1'
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_access(self):
        """测试未认证访问"""
        res = self.client.get('/api/auth/profile/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)