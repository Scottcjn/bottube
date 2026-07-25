from typing import Any, List, Optional


class QueryParamValidator:
    """Validador centralizado de parametros de consulta para la API de BoTTube."""

    @staticmethod
    def validate_string(param: Any, max_length: int = 255) -> Optional[str]:
        """Valida y sanitiza un parametro de tipo string."""
        if param is None:
            return None
        if not isinstance(param, str):
            raise ValueError(f"Expected string, got {type(param).__name__}")
        sanitized = param.strip()
        if len(sanitized) > max_length:
            raise ValueError(f"String exceeds maximum length of {max_length}")
        return sanitized

    @staticmethod
    def validate_integer(
        param: Any, min_val: Optional[int] = None, max_val: Optional[int] = None
    ) -> Optional[int]:
        """Valida y convierte un parametro a entero."""
        if param is None:
            return None
        try:
            value = int(param)
        except (ValueError, TypeError):
            raise ValueError(f"Expected integer, got {type(param).__name__}")
        if min_val is not None and value < min_val:
            raise ValueError(f"Value must be at least {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"Value must be at most {max_val}")
        return value

    @staticmethod
    def validate_boolean(param: Any) -> Optional[bool]:
        """Valida y convierte un parametro a booleano."""
        if param is None:
            return None
        if isinstance(param, bool):
            return param
        if isinstance(param, str):
            if param.lower() in ("true", "1", "yes"):
                return True
            if param.lower() in ("false", "0", "no"):
                return False
        raise ValueError(f"Expected boolean, got {type(param).__name__}")

    @staticmethod
    def validate_enum(param: Any, valid_values: List[str]) -> Optional[str]:
        """Valida que un parametro este en una lista de valores permitidos."""
        if param is None:
            return None
        if param not in valid_values:
            raise ValueError(
                f"Value must be one of: {', '.join(valid_values)}"
            )
        return param