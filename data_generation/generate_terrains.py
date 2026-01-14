import numpy as np
import os
import argparse
from stl import mesh
import sys

# 导入项目中现有的逻辑
sys.path.append(os.path.join(os.path.dirname(__file__), 'python_stl'))
from python_stl.read_grd import create_trimesh

def generate_fbm_noise(nx, ny, octaves=6, persistence=0.5, lacunarity=2.0, seed=None):
    """
    生成分形布朗运动噪声 (fBm)
    """
    if seed is not None:
        np.random.seed(seed)
        
    shape = (nx, ny)
    z = np.zeros(shape)
    amplitude = 1.0
    frequency = 1.0
    
    for _ in range(octaves):
        # 生成随机相位
        tx = np.linspace(0, frequency * 2 * np.pi, nx)
        ty = np.linspace(0, frequency * 2 * np.pi, ny)
        TX, TY = np.meshgrid(tx, ty)
        
        # 模拟随机梯度
        phase = np.random.uniform(0, 2*np.pi)
        angle = np.random.uniform(0, 2*np.pi)
        
        # 叠加随机方向的分量
        z += amplitude * np.sin(TX * np.cos(angle) + TY * np.sin(angle) + phase)
        
        amplitude *= persistence
        frequency *= lacunarity
        
    return z

def apply_thermal_erosion(Z, iterations=5, talus_angle=0.1):
    """
    热侵蚀模拟: 模拟碎石滚落，平滑过于尖锐的坡度
    """
    Z_res = Z.copy()
    rows, cols = Z.shape
    
    for _ in range(iterations):
        # 计算四个方向的坡度
        dz_dx = np.diff(Z_res, axis=1, append=Z_res[:, -1:])
        dz_dy = np.diff(Z_res, axis=0, append=Z_res[-1:, :])
        
        mask_x = np.abs(dz_dx) > talus_angle
        mask_y = np.abs(dz_dy) > talus_angle
        
        Z_res[:, :-1][mask_x[:, :-1]] += dz_dx[:, :-1][mask_x[:, :-1]] * 0.1
        Z_res[:-1, :][mask_y[:-1, :]] += dz_dy[:-1, :][mask_y[:-1, :]] * 0.1
        
    return Z_res

def generate_realistic_terrain(size=1500, res=128, height_max=300):
    # 1. 基础大形 (低频)
    z_base = generate_fbm_noise(res, res, octaves=3, persistence=0.4)
    
    # 2. 细节纹理 (高频)
    z_detail = generate_fbm_noise(res, res, octaves=8, persistence=0.5, lacunarity=2.5)
    
    # 3. 脊状特征 (生成山脊)
    z_ridge = 1.0 - np.abs(generate_fbm_noise(res, res, octaves=4, persistence=0.5))
    
    # 混合地形: 基础 + (脊状 * 细节)
    Z = z_base * 0.6 + (z_ridge ** 2) * z_detail * 0.4
    
    # 归一化高度
    Z -= np.min(Z)
    Z = (Z / np.max(Z)) * height_max
    
    # 4. 热侵蚀平滑
    Z = apply_thermal_erosion(Z, iterations=10)
    
    x = np.linspace(0, size, res)
    y = np.linspace(0, size, res)
    return x, y, Z

def main():
    parser = argparse.ArgumentParser(description='Generate realistic terrain STL files.')
    parser.add_argument('-n', '--num', type=int, default=3)
    parser.add_argument('-s', '--size', type=float, default=1500.0)
    parser.add_argument('-r', '--res', type=int, default=128)
    parser.add_argument('-o', '--outdir', default='realistic_stls')
    parser.add_argument('--height', type=float, default=400.0)
    
    args = parser.parse_args()
    
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    for i in range(args.num):
        seed = np.random.randint(0, 10000)
        x, y, Z = generate_realistic_terrain(size=args.size, res=args.res, height_max=args.height)
        
        # 保存为 STL
        terrain_mesh = create_trimesh(x, y, Z.T, verbose=True)
        filename = os.path.join(args.outdir, "real_terrain_{0:03d}.stl".format(i))
        terrain_mesh.save(filename)
        print("Generated realistic terrain: {0} (Max Height: {1:.1f}m)".format(filename, np.max(Z)))

if __name__ == "__main__":
    main()
