import nextConfig from 'eslint-config-next/core-web-vitals';
import nextTypeScript from 'eslint-config-next/typescript';

const config = [
  ...nextConfig,
  ...nextTypeScript,
  { ignores: ['.next/**', 'generated/**', 'node_modules/**', '.runtime/**'] },
];
export default config;
