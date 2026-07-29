class Bottube < Formula
  include Language::Python::Virtualenv

  desc "Python SDK for BoTTube - the video platform for AI agents"
  homepage "https://bottube.ai"
  url "https://files.pythonhosted.org/packages/source/b/bottube/bottube-1.6.0.tar.gz"
  sha256 "8a8cc92397c32c7915d1913a994a8356e0db7fdfcffa538413633b0c4b531293"
  license "MIT"

  depends_on "python@3.11"
  depends_on "ffmpeg"

  resource "requests" do
    url "https://files.pythonhosted.org/packages/source/r/requests/requests-2.31.0.tar.gz"
    sha256 "942c5a758f98d790eaed1a29cb6eefc7ffb0d1cf7af05c3d2791656dbd6ad1e1"
  end

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"bottube", "--version"
    (testpath/"test.py").write <<~EOS
      from bottube import BoTTubeClient, AMBIENT_PROFILES
      print("Import successful")
      print(f"Scene types: {list(AMBIENT_PROFILES.keys())}")
    EOS
    system Formula["python@3.11"].opt_bin/"python3", testpath/"test.py"
  end
end
