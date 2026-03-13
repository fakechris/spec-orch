class SpecOrch < Formula
  include Language::Python::Virtualenv

  desc "AI-powered specification orchestrator — from discussion to deployed code"
  homepage "https://github.com/fakechris/spec-orch"
  url "https://github.com/fakechris/spec-orch/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "PLACEHOLDER"
  license "MIT"
  head "https://github.com/fakechris/spec-orch.git", branch: "main"

  depends_on "python@3.11"

  # Runtime dependencies — regenerate with:
  #   pip install homebrew-pypi-poet && poet spec-orch
  # Then paste the resource blocks here.

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/spec-orch --version")
  end
end
