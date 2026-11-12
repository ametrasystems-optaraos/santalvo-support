# Unprotect-Build.ps1 - decrypts a Santalvo Support build file (*.enc) made by the CI step
#   openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -salt
# Works in Windows PowerShell 5.1 (.NET 4.7.2+) and PowerShell 7. No OpenSSL needed.
#   . .\Unprotect-Build.ps1 ; Unprotect-Build -In x.exe.enc -Out x.exe -Password $pw
function Unprotect-Build([string]$In, [string]$Out, [string]$Password, [int]$Iterations = 200000) {
    $src = [IO.File]::OpenRead($In)
    try {
        $hdr = New-Object byte[] 16
        if ($src.Read($hdr, 0, 16) -ne 16 -or [Text.Encoding]::ASCII.GetString($hdr, 0, 8) -ne 'Salted__') {
            throw "$In is not an encrypted build file"
        }
        $salt = New-Object byte[] 8; [Array]::Copy($hdr, 8, $salt, 0, 8)
        $kdf = New-Object Security.Cryptography.Rfc2898DeriveBytes(([Text.Encoding]::UTF8.GetBytes($Password)), $salt, $Iterations, [Security.Cryptography.HashAlgorithmName]::SHA256)
        $kiv = $kdf.GetBytes(48); $kdf.Dispose()
        $key = New-Object byte[] 32; $iv = New-Object byte[] 16
        [Array]::Copy($kiv, 0, $key, 0, 32); [Array]::Copy($kiv, 32, $iv, 0, 16)
        $aes = [Security.Cryptography.Aes]::Create()
        $aes.Mode = 'CBC'; $aes.Padding = 'PKCS7'; $aes.Key = $key; $aes.IV = $iv
        $tmp = "$Out.part"
        $dst = [IO.File]::Create($tmp)
        try {
            $cs = New-Object Security.Cryptography.CryptoStream($src, $aes.CreateDecryptor(), 'Read')
            try { $cs.CopyTo($dst) } catch { throw "Wrong password or damaged file: $In" } finally { $cs.Dispose() }
        } finally { $dst.Dispose(); $aes.Dispose() }
        Move-Item -LiteralPath $tmp -Destination $Out -Force
    } finally { $src.Dispose() }
}
